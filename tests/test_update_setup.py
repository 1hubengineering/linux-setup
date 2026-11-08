"""Run the installed updater against a real, local Git remote."""
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UpdateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=str(self.root / 'gitconfig'),
                        GIT_AUTHOR_NAME='Setup Test', GIT_AUTHOR_EMAIL='setup@example.test',
                        GIT_COMMITTER_NAME='Setup Test', GIT_COMMITTER_EMAIL='setup@example.test')
        self.remote = self.root / 'remote.git'
        self.seed = self.root / 'upstream'
        self.checkout = self.root / 'checkout with spaces'
        self.other = self.root / 'unrelated project'
        self.other.mkdir()
        self.git('init', '--bare', '--initial-branch=main', str(self.remote))
        self.git('clone', str(self.remote), str(self.seed))
        for path in ('bin/linux-setup-update', 'scripts/update_setup.py'):
            target = self.seed / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / path, target)
        self.installer('printf old > installed.txt\n')
        self.publish()
        self.git('clone', str(self.remote), str(self.checkout))
        self.entry = self.other / 'installed-updater'
        self.entry.symlink_to(self.checkout / 'bin/linux-setup-update')

    def git(self, *args, cwd=None):
        return subprocess.run(['git', *args], cwd=cwd, env=self.env, capture_output=True, text=True, check=True)

    def installer(self, contents):
        (self.seed / 'install.sh').write_text('#!/bin/sh\nset -eu\n' + contents)

    def publish(self):
        self.git('add', '.', cwd=self.seed)
        self.git('commit', '-m', 'Test setup update', cwd=self.seed)
        self.git('push', 'origin', 'main', cwd=self.seed)

    def update(self):
        return subprocess.run([str(self.entry)], cwd=self.other, env=self.env, capture_output=True, text=True)

    def test_update_from_unrelated_directory_runs_new_installer_and_can_repeat(self):
        self.installer('printf new > installed.txt\npwd > installer-directory.txt\n')
        self.publish()
        for _ in range(2):
            result = self.update()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((self.checkout / 'installed.txt').read_text(), 'new')
            self.assertEqual((self.checkout / 'installer-directory.txt').read_text().strip(), str(self.checkout))
        self.assertFalse((self.other / 'installed.txt').exists())

    def test_update_alias_preserves_the_calling_shell_directory(self):
        if not shutil.which('zsh'):
            self.skipTest('Zsh is required for the alias check')
        data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'linux-setup'
        modules = list((data / 'runtime/usr/lib').glob('*/zsh/*')) + list((data / 'base/zsh/runtime/usr/lib').glob('*/zsh/*'))
        script = 'module_path=(' + ' '.join(shlex.quote(str(p)) for p in modules) + ' $module_path)\n'
        script += 'source "$1"\neval update\nresult=$?\npwd\nexit $result\n'
        environment = dict(self.env, LINUX_SETUP_DIR=str(self.checkout))
        result = subprocess.run(['zsh', '-dfc', script, 'zsh', str(ROOT / 'config/zsh/aliases.zsh')],
                                cwd=self.other, env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], str(self.other))
        self.assertEqual((self.checkout / 'installed.txt').read_text(), 'old')

    def test_failed_pull_does_not_run_installation(self):
        self.remote.rename(self.root / 'offline.git')
        before = self.git('rev-parse', 'HEAD', cwd=self.checkout).stdout
        result = self.update()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Git update failed', result.stderr)
        self.assertEqual(self.git('rev-parse', 'HEAD', cwd=self.checkout).stdout, before)
        self.assertFalse((self.checkout / 'installed.txt').exists())

    def test_conflicting_local_edits_are_preserved_and_installation_is_skipped(self):
        local = self.checkout / 'install.sh'
        local.write_text('#!/bin/sh\nprintf private > installed.txt\n')
        before = local.read_bytes()
        self.installer('printf upstream > installed.txt\n')
        self.publish()
        result = self.update()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(local.read_bytes(), before)
        self.assertFalse((self.checkout / 'installed.txt').exists())

    def test_diverged_history_is_preserved(self):
        (self.checkout / 'private.txt').write_text('local change')
        self.git('add', '.', cwd=self.checkout)
        self.git('commit', '-m', 'Local work', cwd=self.checkout)
        before = self.git('rev-parse', 'HEAD', cwd=self.checkout).stdout
        self.installer('printf upstream > installed.txt\n')
        self.publish()
        result = self.update()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git('rev-parse', 'HEAD', cwd=self.checkout).stdout, before)
        self.assertFalse((self.checkout / 'installed.txt').exists())

    def test_failed_installation_returns_failure_and_can_be_retried(self):
        self.installer('if [ ! -f checkpoint ]; then touch checkpoint; exit 7; fi\nprintf resumed > installed.txt\n')
        self.publish()
        result = self.update()
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertIn('Installation is incomplete', result.stderr)
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.checkout / 'installed.txt').read_text(), 'resumed')


if __name__ == '__main__':
    unittest.main()
