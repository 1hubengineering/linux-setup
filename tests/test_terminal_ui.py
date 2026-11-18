"""Exercise real key input in both keyboard menu backends."""
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import shutil
import signal
import struct
import sys
import termios
import time
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import terminal_ui

FZF_READY = bool(shutil.which("fzf") and terminal_ui.supported_fzf(shutil.which("fzf")))


class KeyboardMenuTests(unittest.TestCase):
    def interact(self, keys, *, multi=True, fallback=False, default=0, preselected=(), allow_skip=False):
        code = (
            "import sys,json; sys.path.insert(0," + repr(str(SCRIPTS)) + "); import terminal_ui as ui; "
            + ("ui.shutil.which=lambda name: None; " if fallback else "")
            + f"\ntry:\n result=ui.select('Keyboard test', [('Alpha','a'),('Beta','b'),('Gamma','c')], multi={multi!r}, default={default}, selected={preselected!r}, allow_skip={allow_skip!r})\n"
            + "except KeyboardInterrupt:\n result='CANCEL'\n"
            + "print('RESULT='+json.dumps(result), flush=True)"
        )
        child, master = pty.fork()
        if child == 0:
            os.execve(sys.executable, [sys.executable, "-c", code], {**os.environ, "TERM": "xterm-256color", "CI": ""})
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 100, 0, 0))
        captured, sent = b"", False
        deadline = time.monotonic() + 8
        try:
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    captured += chunk
                    if b"Keyboard test" in captured and not sent:
                        # Let fzf finish its first draw before sending input.
                        time.sleep(0.15)
                        if len(keys) > 1 and keys.endswith(b"\r"):
                            os.write(master, keys[:-1])
                            time.sleep(0.15)
                            os.write(master, keys[-1:])
                        else:
                            os.write(master, keys)
                        sent = True
                    if b"RESULT=" in captured:
                        payload = captured.split(b"RESULT=", 1)[1].split(b"\r", 1)[0].split(b"\n", 1)[0]
                        try:
                            return json.loads(payload)
                        except ValueError:
                            pass
            self.fail("Menu did not complete: " + captured.decode(errors="replace")[-2000:])
        finally:
            try:
                os.kill(child, signal.SIGTERM)
            except ProcessLookupError:
                pass
            os.close(master)
            os.waitpid(child, 0)

    def test_fallback_preserves_preselected_options(self):
        self.assertEqual(self.interact(b"\r", fallback=True, preselected=('a', 'c')), ['a', 'c'])

    def test_fallback_skip_does_not_accept_preselected_options(self):
        self.assertEqual(self.interact(b"\x13", fallback=True, preselected=('a',), allow_skip=True), [])

    def test_fallback_cancel_is_distinct_from_back(self):
        self.assertEqual(self.interact(b"\x18", fallback=True), 'CANCEL')

    def test_fallback_select_all_and_clear_all(self):
        self.assertEqual(self.interact(b"\x01\r", fallback=True), ['a', 'b', 'c'])
        self.assertEqual(self.interact(b"\x04\r", fallback=True, preselected=('a', 'c')), [])

    @unittest.skipUnless(FZF_READY, "fzf 0.58+ is not installed")
    def test_fzf_preserves_preselected_options(self):
        self.assertEqual(self.interact(b"\r", preselected=('a', 'c')), ['a', 'c'])

    @unittest.skipUnless(FZF_READY, "fzf 0.58+ is not installed")
    def test_fzf_skip_does_not_accept_preselected_options(self):
        self.assertEqual(self.interact(b"\x13", preselected=('a',), allow_skip=True), [])

    @unittest.skipUnless(FZF_READY, "fzf 0.58+ is not installed")
    def test_fzf_cancel_is_distinct_from_back(self):
        self.assertEqual(self.interact(b"\x18"), 'CANCEL')

    def test_fallback_arrow_space_and_enter_select_multiple(self):
        # Space selects Alpha and moves to Beta; Down skips Beta to Gamma.
        self.assertEqual(self.interact(b" \x1bOB \r", fallback=True), ["a", "c"])

    def test_fallback_enter_without_checks_selects_nothing(self):
        self.assertEqual(self.interact(b"\r", fallback=True), [])

    def test_fallback_escape_cancels(self):
        self.assertIsNone(self.interact(b"\x1b", fallback=True))

    @unittest.skipUnless(FZF_READY, "fzf 0.58+ is not installed")
    def test_fzf_arrow_space_and_enter_select_multiple(self):
        self.assertEqual(self.interact(b" \x1b[B \r"), ["a", "c"])

    @unittest.skipUnless(FZF_READY, "fzf 0.58+ is not installed")
    def test_fzf_enter_without_checks_selects_nothing(self):
        self.assertEqual(self.interact(b"\r"), [])

    @unittest.skipUnless(FZF_READY, "fzf 0.58+ is not installed")
    def test_fzf_search_matches_visible_label(self):
        self.assertEqual(self.interact(b"Beta\r", multi=False), "b")

    @unittest.skipUnless(FZF_READY, "fzf 0.58+ is not installed")
    def test_fzf_single_select_honors_safe_default(self):
        self.assertEqual(self.interact(b"\r", multi=False, default=1), "b")


if __name__ == "__main__":
    unittest.main()
