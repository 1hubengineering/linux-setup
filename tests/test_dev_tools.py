import contextlib
import io
import urllib.error
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import dev_tools
import shell_manager


class DeveloperTests(unittest.TestCase):
    def test_existing_authentication_never_runs_login(self):
        with patch.object(sys.stdin, 'isatty', return_value=True), patch.object(dev_tools.shutil, 'which', side_effect=lambda n: '/bin/' + n), patch.object(dev_tools.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            dev_tools.authenticate()
        self.assertEqual([c.args[0] for c in run.call_args_list], [['codex', 'login', 'status'], ['claude', 'auth', 'status']])

    def test_missing_login_uses_requested_device_flow(self):
        with patch.object(sys.stdin, 'isatty', return_value=True), patch.object(dev_tools.shutil, 'which', return_value='/bin/codex'), patch.object(dev_tools.subprocess, 'run', side_effect=[Mock(returncode=1), Mock(returncode=0)]) as run:
            dev_tools.authenticate('codex', device=True)
        self.assertEqual(run.call_args.args[0], ['codex', 'login', '--device-auth'])

    def test_api_key_is_sent_on_stdin_without_printing_or_arguments(self):
        secret = 'example-placeholder-secret'
        with patch.object(sys.stdin, 'isatty', return_value=True), patch.object(dev_tools.shutil, 'which', return_value='/bin/codex'), patch.dict(os.environ, {'OPENAI_API_KEY': secret}), patch.object(dev_tools.subprocess, 'run', side_effect=[Mock(returncode=1), Mock(returncode=0)]) as run, patch.object(sys, 'stdout', new_callable=io.StringIO) as output:
            dev_tools.authenticate('codex', method='api-key')
        self.assertEqual(run.call_args.args[0], ['codex', 'login', '--with-api-key'])
        self.assertEqual(run.call_args.kwargs['input'], secret + '\n')
        self.assertNotIn(secret, output.getvalue())
        self.assertNotIn(secret, ' '.join(run.call_args.args[0]))

    def test_selective_cli_install_does_not_require_uv_or_install_other_tools(self):
        with patch.object(dev_tools.shutil, 'which', side_effect=lambda name: None if name in ('uv', 'codex') else '/bin/' + name), patch.object(dev_tools, 'run') as run:
            self.assertEqual(dev_tools.install(selected=['codex']), [])
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][-1], '@openai/codex@latest')

    def test_auth_never_blocks_noninteractive_install(self):
        with patch.object(sys.stdin, 'isatty', return_value=False), patch.object(dev_tools.subprocess, 'run') as run:
            with self.assertRaises(RuntimeError):
                dev_tools.authenticate()
        run.assert_not_called()

    def test_existing_clis_are_kept(self):
        with patch.object(dev_tools.shutil, 'which', side_effect=lambda n: '/bin/' + n), patch.object(dev_tools, 'run') as run:
            dev_tools.install()
        run.assert_called_once_with(['/bin/uv', 'python', 'install'])

    def test_mcp_inspection_failure_does_not_modify_config(self):
        with patch.object(dev_tools.shutil, 'which', return_value='/bin/codex'), patch.object(dev_tools.subprocess, 'run', return_value=Mock(returncode=1, stdout='', stderr='invalid config')) as run:
            with self.assertRaises(RuntimeError):
                dev_tools.mcp('codex')
        self.assertEqual(run.call_count, 1)

    def test_session_toggle_uses_running_shell_and_replaces_process(self):
        with patch.object(shell_manager.shutil, 'which', side_effect=lambda n: '/bin/' + n), patch.object(shell_manager.os, 'execv') as execute, patch.dict(os.environ, {'SHELL': '/bin/zsh'}):
            shell_manager.main(['--current', 'bash'])
            execute.assert_called_once_with('/bin/zsh', ['/bin/zsh', '-l'])

    def test_default_shell_changes_account_only_through_chsh(self):
        account = Mock(pw_shell='/bin/bash')
        with patch.object(shell_manager.pwd, 'getpwuid', return_value=account), patch.object(shell_manager.shutil, 'which', return_value='/bin/zsh'), patch.object(Path, 'read_text', return_value='/bin/bash\n/bin/zsh\n'), patch.object(shell_manager.subprocess, 'run') as run, patch.object(shell_manager.os, 'execv') as execute:
            shell_manager.main(['--default', 'zsh'])
        run.assert_called_once_with(['chsh', '-s', '/bin/zsh'], check=True)
        execute.assert_not_called()

    def test_unregistered_default_shell_never_calls_chsh(self):
        with patch.object(shell_manager.shutil, 'which', return_value='/private/zsh'), patch.object(Path, 'read_text', return_value='/bin/bash\n'), patch.object(shell_manager.subprocess, 'run') as run:
            with self.assertRaises(RuntimeError):
                shell_manager.main(['--default', 'zsh'])
        run.assert_not_called()

    def test_missing_cli_does_not_report_authentication_complete(self):
        with patch.object(sys.stdin, 'isatty', return_value=True), patch.object(dev_tools.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'Missing CLIs'):
                dev_tools.authenticate('codex')

    def test_interactive_initialization_offers_tools_and_auth_once(self):
        import setup
        deploy = Mock(state={'github_setup_prompted': True, 'skills_setup_prompted': True})
        with patch('git_profiles.configure_identity'), patch('git_profiles.ask_yes', return_value=True) as ask, patch.object(dev_tools, 'install', return_value=[]) as install, patch.object(dev_tools, 'authenticate') as auth:
            setup.interactive_setup({}, 'linux-x86_64', deploy)
            setup.interactive_setup({}, 'linux-x86_64', deploy)
        self.assertEqual(ask.call_count, 2)
        install.assert_called_once()
        auth.assert_called_once()

    def test_failed_developer_setup_is_retried(self):
        import setup
        deploy = Mock(state={'github_setup_prompted': True, 'skills_setup_prompted': True})
        with patch('git_profiles.ask_yes', return_value=True), patch.object(dev_tools, 'install', side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):
                setup.interactive_setup({}, 'linux-x86_64', deploy)
        self.assertNotIn('developer_setup_prompted', deploy.state)

    def test_claude_403_is_reported_and_graphify_still_installs(self):
        def which(name):
            return None if name in ('claude', 'graphify') else '/bin/' + name
        with patch.object(dev_tools.shutil, 'which', side_effect=which), patch.object(dev_tools, 'run') as run, patch.object(dev_tools.urllib.request, 'urlopen', side_effect=urllib.error.HTTPError('https://claude.ai/install.sh', 403, 'Forbidden', {}, None)), patch.object(sys, 'stderr', new_callable=io.StringIO) as errors:
            self.assertEqual(dev_tools.install(), ['claude'])
        run.assert_any_call(['/bin/uv', 'tool', 'install', 'graphifyy'])
        self.assertIn('HTTP 403', errors.getvalue())
        self.assertIn('retry dev-tools install', errors.getvalue())
        self.assertFalse(any(call.args[0][0] == 'bash' for call in run.call_args_list))

    def test_explicit_developer_attempt_is_not_repeated_by_interactive_setup(self):
        import setup
        deploy = Mock(state={'github_setup_prompted': True, 'skills_setup_prompted': True})
        with patch('git_profiles.configure_identity'), patch('git_profiles.ask_yes') as ask, patch.object(dev_tools, 'install') as install:
            self.assertEqual(setup.interactive_setup({}, 'linux-x86_64', deploy, developer_attempted=True), [])
        install.assert_not_called()
        ask.assert_not_called()
        self.assertNotIn('developer_setup_prompted', deploy.state)

    def test_standalone_install_returns_nonzero_for_partial_failure(self):
        with patch.object(dev_tools, 'install', return_value=['claude']):
            self.assertEqual(dev_tools.main(['install']), 1)

    def test_bash_startup_keeps_original_files_and_restores_them(self):
        import setup
        with tempfile.TemporaryDirectory() as temporary, contextlib.ExitStack() as stack:
            home = Path(temporary)
            for name, value in [('HOME', home), ('DATA', home / 'data'), ('STATE', home / 'state')]:
                stack.enter_context(patch.object(setup, name, value))
            (home / '.bashrc').write_text('export ORIGINAL_RC=yes\n')
            (home / '.bash_profile').write_text('export ORIGINAL_PROFILE=yes\n')
            deploy = setup.Deployment()
            setup.install_bash(deploy)
            before = dict(deploy.state['links'])
            setup.install_bash(deploy)
            self.assertEqual(before, deploy.state['links'])
            result = subprocess.check_output(['bash', '-c', 'source "$1"; printf "%s" "$ORIGINAL_RC"', 'bash', str(home / '.bashrc')], text=True)
            self.assertEqual(result, 'yes')
            deploy.restore()
            self.assertEqual((home / '.bashrc').read_text(), 'export ORIGINAL_RC=yes\n')
            self.assertEqual((home / '.bash_profile').read_text(), 'export ORIGINAL_PROFILE=yes\n')


if __name__ == '__main__':
    unittest.main()
