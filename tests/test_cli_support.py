"""Check public CLI contracts without loading settings or invoking program actions."""
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cli_support
import console
import setup

COMMANDS = [ROOT / 'install.sh', ROOT / 'uninstall.sh'] + [p for p in sorted((ROOT / 'bin').iterdir()) if p.is_file()]


def help_tokens(text):
    # Older argparse versions use a different heading and repeat metavars for aliases.
    text = text.replace('\noptional arguments:\n', '\noptions:\n')
    text = re.sub(r'(?m)^([ \t]+-\w) ([A-Z][A-Z0-9_]*), (--[\w-]+) \2\b', r'\1, \3 \2', text)
    return text.split()


class CliTests(unittest.TestCase):
    def test_all_public_commands_offer_read_only_help_and_consistent_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            env = {**os.environ, 'HOME': temporary, 'XDG_CONFIG_HOME': str(home / 'config'), 'XDG_STATE_HOME': str(home / 'state'), 'XDG_CACHE_HOME': str(home / 'cache'), 'XDG_DATA_HOME': str(home / 'data')}
            for command in COMMANDS:
                for flag in ('--help', '--version'):
                    with self.subTest(command=command.name, flag=flag):
                        result = subprocess.run([str(command), flag], cwd=temporary, env=env, capture_output=True, text=True)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stderr, '')
                        self.assertIn(command.name, result.stdout)
                        if flag == '--version':
                            self.assertIn(cli_support.version(), result.stdout)
                        else:
                            self.assertIn('--completion', result.stdout)
            self.assertEqual(list(home.iterdir()), [])

    def test_generated_help_matches_real_parsers(self):
        for command in COMMANDS:
            with self.subTest(command=command.name):
                result = subprocess.run([str(command), '--help'], env={**os.environ, 'LINUX_SETUP_BUILD_CLI': '1'}, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                snapshot = (ROOT / 'config/cli-help' / (command.name + '.txt')).read_text()
                self.assertEqual(help_tokens(result.stdout), help_tokens(snapshot))

    def test_completion_scripts_use_real_subcommands_and_argument_choices(self):
        for shell in ('bash', 'zsh', 'fish'):
            result = subprocess.run([str(ROOT / 'bin/dev-tools'), '--completion', shell], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('workflow', result.stdout)
            self.assertIn('claude', result.stdout)
            self.assertIn('openspec', result.stdout)
            self.assertNotIn('\033', result.stdout)
            self.assertIn(result.stdout, (ROOT / 'config/completions' / ('linux-setup.' + shell)).read_text())

    def test_metadata_actions_bypass_installer_operation_lock(self):
        for flag in ('--version', '--completion'):
            arguments = ['setup.py', flag] + (['bash'] if flag == '--completion' else [])
            with patch.object(sys, 'argv', arguments), patch.object(setup, 'operation_lock') as lock, patch.object(setup, '_main', return_value=0):
                self.assertEqual(setup.main(), 0)
                lock.assert_not_called()

    def test_ci_never_opens_the_wizard_or_uses_terminal_color(self):
        with patch.dict(os.environ, {'CI': '1', 'TERM': 'xterm'}), patch.object(sys.stdin, 'isatty', return_value=True), patch.object(sys.stdout, 'isatty', return_value=True):
            self.assertFalse(cli_support.can_prompt())
            self.assertFalse(setup.wants_wizard([]))
            self.assertFalse(console.interactive())

    def test_explicit_authentication_fails_fast_in_ci(self):
        import dev_tools
        with patch.dict(os.environ, {'CI': '1'}), patch.object(sys.stdin, 'isatty', return_value=True), patch.object(dev_tools.subprocess, 'run') as run:
            with self.assertRaises(RuntimeError):
                dev_tools.authenticate('codex')
        run.assert_not_called()

    def test_unknown_skill_manager_flag_returns_usage_error_before_prompt(self):
        result = subprocess.run([str(ROOT / 'bin/skill-manager'), '--not-a-real-option'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('unrecognized arguments', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_bash_completion_returns_contextual_values_without_running_tools(self):
        source = str(ROOT / 'config/completions/linux-setup.bash')
        for words, current, function, expected in [
            ('dev-tools auth c', 2, '_linux_setup_dev_tools', {'codex', 'claude'}),
            ('dev-tools --completion z', 2, '_linux_setup_dev_tools', {'zsh'}),
            ('install.sh --wiz', 1, '_linux_setup_install_sh', {'--wizard'}),
        ]:
            code = 'source "$1"; COMP_WORDS=(' + words + '); COMP_CWORD=' + str(current) + '; ' + function + '; printf "%s\\n" "${COMPREPLY[@]}"'
            result = subprocess.run(['bash', '--noprofile', '--norc', '-c', code, 'bash', source], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(set(result.stdout.splitlines()), expected)

    @unittest.skipUnless(shutil.which('zsh'), 'Zsh is required')
    def test_zsh_completion_can_be_loaded_and_called(self):
        code = 'compdef() { :; }; compadd() { printf "%s\\n" "$@"; }; _files() { return 1; }; source "$1"; words=(dev-tools auth c); CURRENT=3; _linux_setup_dev_tools'
        result = subprocess.run(['zsh', '-dfc', code, 'zsh', str(ROOT / 'config/completions/linux-setup.zsh')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('codex', result.stdout)
        self.assertIn('claude', result.stdout)

    @unittest.skipUnless(shutil.which('fish'), 'Fish is required')
    def test_fish_completion_syntax(self):
        result = subprocess.run(['fish', '-n', str(ROOT / 'config/completions/linux-setup.fish')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
