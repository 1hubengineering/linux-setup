"""Exercise the default installer entry point in an actual terminal."""
import os
import fcntl
import struct
import termios
from pathlib import Path
import pty
import select
import signal
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WizardCliTests(unittest.TestCase):
    def test_default_interactive_cancel_precedes_any_state_or_config_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            env = {**os.environ, 'HOME': temporary, 'TERM': 'xterm-256color', 'PYTHONDONTWRITEBYTECODE': '1', 'CI': ''}
            for variable, suffix in [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'), ('XDG_STATE_HOME', 'state'), ('XDG_CACHE_HOME', 'cache')]:
                env[variable] = str(home / suffix)
            child, master = pty.fork()
            if child == 0:
                os.execve(sys.executable, [sys.executable, str(ROOT / 'scripts/setup.py')], env)
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 110, 0, 0))
            captured, sent = b'', False
            try:
                deadline = time.monotonic() + 12
                while time.monotonic() < deadline:
                    if select.select([master], [], [], 0.1)[0]:
                        try:
                            chunk = os.read(master, 65536)
                        except OSError:
                            break
                        if not chunk:
                            break
                        captured += chunk
                        if b'Programs:' in captured and not sent:
                            time.sleep(0.2)
                            os.write(master, b'\x18')
                            sent = True
                self.assertTrue(sent, captured.decode(errors='replace')[-2000:])
                self.assertIn(b'Setup cancelled; no files were changed.', captured)
                self.assertEqual(list(home.iterdir()), [])
            finally:
                try:
                    os.kill(child, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                os.close(master)
                os.waitpid(child, 0)


if __name__ == '__main__':
    unittest.main()
