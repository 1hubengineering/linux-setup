"""Verify redirected logs, terminal sizing, and reduced-motion cleanup."""
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import console


class Terminal(io.StringIO):
    def isatty(self):
        return True


class ConsoleTests(unittest.TestCase):
    def test_redirected_logs_have_labels_and_borders_without_escape_codes(self):
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            console.section('Installation summary', stream=output)
            console.status('error', 'claude: HTTP 403', stream=output)
            console.table(('Tool', 'Result'), [('claude', 'INCOMPLETE')], stream=output)
        text = output.getvalue()
        self.assertNotIn('\033', text)
        self.assertIn('[INCOMPLETE] claude: HTTP 403', text)
        self.assertIn('| Tool', text)

    def test_no_color_keeps_status_labels(self):
        output = Terminal()
        with patch.dict(os.environ, {'TERM': 'xterm', 'NO_COLOR': ''}, clear=True):
            console.status('ok', 'ready', stream=output)
        self.assertIn('OK', output.getvalue())
        self.assertNotIn('\033', output.getvalue())

    def test_plain_mode_disables_borders_colors_and_animation(self):
        output = Terminal()
        with patch.dict(os.environ, {'TERM': 'xterm', 'LINUX_SETUP_PLAIN': '1'}, clear=True), patch.object(console.sys, 'stderr', output), patch.object(console.threading, 'Thread') as thread:
            console.section('Summary', stream=output)
            console.table(('Tool', 'Result'), [('claude', 'INCOMPLETE')], stream=output)
            with console.busy('download'):
                pass
        self.assertNotIn('\033', output.getvalue())
        self.assertNotIn('─', output.getvalue())
        self.assertIn('Tool: claude | Result: INCOMPLETE', output.getvalue())
        thread.assert_not_called()

    def test_wide_characters_and_long_paths_fit_table(self):
        output = Terminal()
        with patch.dict(os.environ, {'TERM': 'xterm', 'NO_COLOR': '1'}, clear=True), patch.object(console.shutil, 'get_terminal_size', return_value=os.terminal_size((60, 24))):
            console.table(('Tool', 'Details'), [('Python', '/home/' + '子目录/' * 20)], stream=output)
        self.assertTrue(all(console.width(line) <= 59 for line in output.getvalue().splitlines()))

    def test_narrow_terminal_uses_wrapped_rows(self):
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), patch.object(console.shutil, 'get_terminal_size', return_value=os.terminal_size((30, 24))):
            console.table(('Step', 'Result'), [('developer tools', 'INCOMPLETE')], stream=output)
        self.assertTrue(all(len(line) <= 29 for line in output.getvalue().splitlines()))
        self.assertIn('developer tools', output.getvalue())

    def test_reduced_motion_and_ci_do_not_start_spinner(self):
        for environment in ({'LINUX_SETUP_NO_ANIMATION': '1'}, {'CI': '1'}):
            with patch.dict(os.environ, {'TERM': 'xterm', **environment}, clear=True), patch.object(console.sys, 'stderr', Terminal()), patch.object(console.threading, 'Thread') as thread:
                with console.busy('download'):
                    pass
                thread.assert_not_called()

    def test_standalone_helpers_find_shared_console_module(self):
        root = Path(__file__).resolve().parents[1]
        for command in ([str(root / 'bin/dev-tools'), '--help'], [str(root / 'bin/linux-setup-guide')]):
            result = subprocess.run(command, cwd='/tmp', capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_spinner_is_cleared_when_work_fails(self):
        output = Terminal()
        with patch.dict(os.environ, {'TERM': 'xterm'}, clear=True), patch.object(console.sys, 'stderr', output):
            with self.assertRaises(RuntimeError):
                with console.busy('download'):
                    raise RuntimeError('offline')
        self.assertTrue(output.getvalue().endswith('\r\033[2K'))


if __name__ == '__main__':
    unittest.main()
