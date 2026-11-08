import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("git_profiles", ROOT / "scripts/git_profiles.py")
profiles = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profiles)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"HOME": str(self.root), "XDG_CONFIG_HOME": str(self.root / "config"), "GIT_CONFIG_NOSYSTEM": "1"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_identity_only_fills_missing_global_values(self):
        subprocess.run(["git", "config", "--global", "user.name", "Existing"], check=True)
        with patch("builtins.input", return_value="person@example.com") as prompt:
            profiles.configure_identity()
        self.assertEqual(prompt.call_count, 1)
        self.assertEqual(subprocess.check_output(["git", "config", "--global", "user.name"], text=True).strip(), "Existing")
        self.assertEqual(subprocess.check_output(["git", "config", "--global", "user.email"], text=True).strip(), "person@example.com")

    def test_add_existing_account_saves_only_author_details(self):
        with patch.object(profiles.shutil, "which", return_value="/usr/bin/gh"), patch("builtins.input", side_effect=["n", "alice", "Alice Example", "alice@example.com"]), patch.object(profiles.subprocess, "run") as run:
            profiles.add_profile()
        run.assert_not_called()
        self.assertEqual(profiles.load_profiles(), {"alice": {"name": "Alice Example", "email": "alice@example.com"}})
        self.assertEqual(profiles.profiles_path().stat().st_mode & 0o777, 0o600)

    def test_add_new_account_runs_github_login(self):
        with patch.object(profiles.shutil, "which", return_value="/usr/bin/gh"), patch("builtins.input", side_effect=["y", "alice", "Alice", "a@example.com"]), patch.object(profiles.subprocess, "run") as run:
            profiles.add_profile()
        run.assert_called_once_with(["gh", "auth", "login"], check=True)

    def test_declining_replace_keeps_profile(self):
        original = {"alice": {"name": "Alice", "email": "a@example.com"}}
        profiles.save_profiles(original)
        with patch.object(profiles.shutil, "which", return_value="/usr/bin/gh"), patch("builtins.input", side_effect=["n", "alice", "n"]):
            profiles.add_profile()
        self.assertEqual(profiles.load_profiles(), original)

    def test_use_changes_only_repository_identity_and_switches_account(self):
        repo = self.root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        profiles.save_profiles({"alice": {"name": "Alice Example", "email": "alice@example.com"}})
        calls = []
        actual_run = subprocess.run
        def run(command, **kwargs):
            if command[0] == "gh":
                calls.append(command)
                return subprocess.CompletedProcess(command, 0)
            return actual_run(command, **kwargs)
        old = Path.cwd()
        try:
            os.chdir(repo)
            with patch.object(profiles.shutil, "which", return_value="/usr/bin/gh"), patch.object(profiles.subprocess, "run", side_effect=run):
                profiles.use_profile("alice")
        finally:
            os.chdir(old)
        self.assertEqual(calls, [["gh", "auth", "switch", "--hostname", "github.com", "--user", "alice"]])
        self.assertEqual(subprocess.check_output(["git", "-C", str(repo), "config", "--local", "user.email"], text=True).strip(), "alice@example.com")
        self.assertFalse((self.root / ".gitconfig").exists())

    def test_failed_switch_leaves_repository_identity_unchanged(self):
        profiles.save_profiles({"alice": {"name": "Alice", "email": "a@example.com"}})
        def run(command, **kwargs):
            if command[0] == "gh":
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0)
        with patch.object(profiles.shutil, "which", return_value="/usr/bin/gh"), patch.object(profiles.subprocess, "run", side_effect=run) as mock:
            with self.assertRaises(subprocess.CalledProcessError):
                profiles.use_profile("alice")
        self.assertEqual(mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
