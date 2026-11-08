"""Exercise retries against real files and executables in an isolated home."""
from contextlib import ExitStack
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("recovery_setup", ROOT / "scripts/setup.py")
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        for name, suffix in {"HOME": "home", "CONFIG": "config", "DATA": "data/linux-setup",
                             "STATE": "state/linux-setup", "CACHE": "cache/linux-setup", "BIN": "bin"}.items():
            stack.enter_context(patch.object(setup, name, self.root / suffix))
        stack.enter_context(patch.object(setup, "find_tool", return_value=None))
        self.deploy = setup.Deployment()

    def artifact(self, name, version="1"):
        source = self.root / f"{name}-{version}.bin"
        source.write_text(f"#!/bin/sh\nprintf '%s\\n' '{name}-{version}'\n")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        item = {"version": version, "platforms": {"linux-x86_64": {
            "name": source.name, "url": "https://example.invalid/" + source.name, "sha256": digest}}}
        return source, item

    def install(self, tools, download):
        with patch.object(setup, "download", side_effect=download):
            return setup.install_tools({"tools": tools, "plugins": {}}, "linux-x86_64", self.deploy)

    def output(self, name):
        return subprocess.check_output([str(setup.BIN / name)], text=True).strip()

    def test_failed_download_does_not_block_other_tools_and_retry_reuses_successes(self):
        artifacts = {name: self.artifact(name) for name in ("alpha", "beta", "gamma")}
        attempts = []
        fail = True

        def download(url, digest, filename):
            name = filename.split('-')[0]
            attempts.append(name)
            if name == "beta" and fail:
                raise OSError("network disconnected")
            return artifacts[name][0]

        tools = {name: pair[1] for name, pair in artifacts.items()}
        self.assertEqual(self.install(tools, download), ["beta"])
        self.assertEqual(self.output("alpha"), "alpha-1")
        self.assertEqual(self.output("gamma"), "gamma-1")
        first = json.loads(self.deploy.path.read_text())["programs"]
        self.deploy = setup.Deployment()
        fail = False
        self.assertEqual(self.install(tools, download), [])
        self.assertEqual(attempts, ["alpha", "beta", "gamma", "beta"])
        self.assertEqual(self.output("beta"), "beta-1")
        for name in ("alpha", "gamma"):
            self.assertEqual(self.deploy.state["programs"][name]["fingerprints"], first[name]["fingerprints"])
        self.assertFalse(list(setup.STATE.glob("backups/**/*")))

    def test_interruption_after_bundle_rename_reuses_verified_bundle(self):
        source, item = self.artifact("alpha")
        with patch.object(setup, "download", return_value=source), \
             patch.object(setup, "record_complete", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                setup.install_tools({"tools": {"alpha": item}, "plugins": {}}, "linux-x86_64", self.deploy)
        self.deploy = setup.Deployment()
        pending = self.deploy.state["programs"]["alpha"]["pending_bundle"]
        self.assertTrue(Path(pending["path"]).is_dir())
        with patch.object(setup, "download") as download:
            self.assertEqual(self.install({"alpha": item}, download), [])
            download.assert_not_called()
        entry = self.deploy.state["programs"]["alpha"]
        self.assertEqual(entry["fingerprints"][entry["active_path"]], setup.fingerprint(entry["active_path"]))
        self.assertNotIn("pending_bundle", entry)
        self.assertEqual(self.output("alpha"), "alpha-1")

    def test_interrupted_link_keeps_original_backup_and_is_restorable(self):
        source = self.root / "new-config"
        source.write_text("managed config")
        target = self.root / "old-config"
        target.write_text("original config")
        with patch.object(Path, "symlink_to", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.deploy.link(source, target)
        self.assertFalse(target.exists())
        saved = self.deploy.state["links"][str(target)]["backup"]
        self.assertEqual(Path(saved).read_text(), "original config")
        self.deploy = setup.Deployment()
        self.deploy.link(source, target)
        self.deploy.link(source, target)
        self.assertEqual(self.deploy.state["links"][str(target)]["backup"], saved)
        self.assertEqual([p for p in (setup.STATE / "backups").rglob('*') if p.is_file()], [Path(saved)])
        self.deploy.restore()
        self.assertEqual(target.read_text(), "original config")

    def test_missing_managed_link_repair_preserves_original_backup(self):
        source, target = self.root / "source", self.root / "target"
        source.write_text("managed")
        target.write_text("original")
        self.deploy.link(source, target)
        backup = self.deploy.state["links"][str(target)]["backup"]
        target.unlink()
        self.deploy = setup.Deployment()
        self.deploy.link(source, target)
        self.assertEqual(self.deploy.state["links"][str(target)]["backup"], backup)
        self.deploy.restore()
        self.assertEqual(target.read_text(), "original")

    def test_changed_file_after_interruption_is_preserved(self):
        source, target = self.root / "source", self.root / "target"
        source.write_text("new")
        target.write_text("original")
        with patch.object(Path, "symlink_to", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.deploy.link(source, target)
        target.write_text("edited since failure")
        with self.assertRaisesRegex(RuntimeError, "Keeping a file changed"):
            setup.Deployment().link(source, target)
        self.assertEqual(target.read_text(), "edited since failure")

    def test_updates_require_consent_and_failed_approved_update_resumes_without_reprompt(self):
        first, old = self.artifact("alpha")
        second, new = self.artifact("alpha", "2")
        self.assertEqual(self.install({"alpha": old}, lambda *args: first), [])
        (setup.BIN / "alpha").unlink()
        with patch.object(sys.stdin, "isatty", return_value=False), patch("terminal_ui.confirm") as confirm:
            self.assertEqual(self.install({"alpha": new}, lambda *args: self.fail("Unapproved download")), [])
            confirm.assert_not_called()
        with patch.object(sys.stdin, "isatty", return_value=True), patch.object(sys.stdout, "isatty", return_value=True), \
             patch("terminal_ui.confirm", return_value=False) as confirm:
            self.assertEqual(self.install({"alpha": new}, lambda *args: self.fail("Declined download")), [])
            confirm.assert_called_once()
        self.assertEqual(self.output("alpha"), "alpha-1")
        def failed_download(*args):
            raise OSError("offline")
        with patch.object(sys.stdin, "isatty", return_value=True), patch.object(sys.stdout, "isatty", return_value=True), \
             patch("terminal_ui.confirm", return_value=True):
            self.assertEqual(self.install({"alpha": new}, failed_download), ["alpha"])
        self.assertEqual(self.output("alpha"), "alpha-1")
        self.deploy = setup.Deployment()
        with patch.object(sys.stdin, "isatty", return_value=False), patch("terminal_ui.confirm") as confirm:
            self.assertEqual(self.install({"alpha": new}, lambda *args: second), [])
            confirm.assert_not_called()
        self.assertEqual(self.output("alpha"), "alpha-2")
        self.assertNotIn("requested_version", self.deploy.state["programs"]["alpha"])
        self.assertTrue((setup.DATA / "tools/alpha/1-linux-x86_64/alpha").is_file())

    def test_approved_update_interrupted_after_publish_uses_new_pending_path(self):
        first, old = self.artifact("alpha")
        second, new = self.artifact("alpha", "2")
        self.install({"alpha": old}, lambda *args: first)
        with patch.object(sys.stdin, "isatty", return_value=True), patch.object(sys.stdout, "isatty", return_value=True), \
             patch("terminal_ui.confirm", return_value=True), patch.object(setup, "record_complete", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.install({"alpha": new}, lambda *args: second)
        self.assertEqual(self.output("alpha"), "alpha-1")
        self.deploy = setup.Deployment()
        self.assertEqual(self.install({"alpha": new}, lambda *args: self.fail("Bundle downloaded twice")), [])
        self.assertEqual(self.output("alpha"), "alpha-2")

    def test_uv_companion_link_is_repaired_without_bootstrap_or_download(self):
        folder = setup.DATA / "tools/uv/1-linux-x86_64"
        folder.mkdir(parents=True)
        for name in ("uv", "uvx"):
            (folder / name).write_text("binary")
        self.deploy.record_program("uv", paths=[folder], binaries=["uv", "uvx"], active_path=str(folder), version="1")
        item = {"install_if_missing": True, "version": "2", "binaries": ["uv", "uvx"]}
        with patch.object(setup, "find_tool", return_value=str(folder / "uv")), patch.object(setup, "run") as run:
            self.assertEqual(self.install({"uv": item}, lambda *args: self.fail("uv reinstalled")), [])
            run.assert_not_called()
        self.assertEqual((setup.BIN / "uvx").resolve(), folder / "uvx")

    def test_existing_external_program_is_kept_without_version_probe(self):
        _, item = self.artifact("alpha")
        with patch.object(setup, "find_tool", return_value="/existing/alpha"), patch.object(setup, "run") as run:
            self.assertEqual(self.install({"alpha": item}, lambda *args: self.fail("External program replaced")), [])
            run.assert_not_called()
        self.assertFalse(self.deploy.state["programs"]["alpha"]["owned"])
        self.assertFalse((setup.BIN / "alpha").exists())

    def test_journal_records_failure_interrupt_and_successful_retry(self):
        journal = setup.InstallationRun(self.deploy, "full")
        journal.step("base tools", lambda: ["zsh"])
        journal.step("configuration", lambda: None)
        self.assertEqual(journal.finish(), ["zsh"])
        self.deploy = setup.Deployment()
        journal = setup.InstallationRun(self.deploy, "full")
        def interrupt():
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            journal.step("tools", interrupt)
        record = setup.Deployment().state["installations"]["full"]
        self.assertEqual(record["status"], "incomplete")
        self.assertEqual(record["steps"]["configuration"]["status"], "complete")
        self.deploy = setup.Deployment()
        journal = setup.InstallationRun(self.deploy, "full")
        for name in ("base tools", "tools", "configuration"):
            journal.step(name, lambda: [])
        self.assertEqual(journal.finish(), [])
        record = setup.Deployment().state["installations"]["full"]
        self.assertEqual(record["status"], "complete")
        self.assertNotIn("current_step", record)

    def test_lock_rejects_concurrent_mutation_and_releases_on_interrupt(self):
        with self.assertRaises(KeyboardInterrupt):
            with setup.operation_lock():
                with self.assertRaisesRegex(RuntimeError, "Another linux-setup"):
                    with setup.operation_lock():
                        self.fail("Concurrent operation acquired the lock")
                raise KeyboardInterrupt
        with setup.operation_lock():
            self.assertFalse(setup.STATE.joinpath("deployment.json").exists())

    def test_new_process_resumes_after_abrupt_exit_without_redownloading(self):
        source, item = self.artifact("alpha")
        # os._exit bypasses cleanup and exception handlers, like a terminated process.
        script = "\n".join([
            "import os, sys",
            f"sys.path.insert(0, {str(ROOT / 'scripts')!r})",
            "import setup, preflight",
            *[f"setup.{name} = setup.Path({str(getattr(setup, name))!r})" for name in ("HOME", "CONFIG", "DATA", "STATE", "CACHE", "BIN")],
            "preflight.check = lambda *args, **kwargs: []",
            "setup.migrate_legacy = lambda: None",
            "setup.install_base = lambda deploy: []",
            "setup.install_config = lambda deploy: None",
            "original_tools = setup.install_tools",
            f"mini_lock = {{'tools': {{'alpha': {item!r}}}, 'plugins': {{}}}}",
            "setup.install_tools = lambda lock, key, deploy: original_tools(mini_lock, key, deploy)",
            "setup.find_tool = lambda name: None",
            f"setup.download = lambda *args: setup.Path({str(source)!r})",
            "sys.argv = ['setup.py', '--skip-mcp']",
        ])
        failure = script + "\nsetup.record_complete = lambda *args, **kwargs: os._exit(87)\nsys.exit(setup.main())\n"
        result = subprocess.run([sys.executable, '-c', failure], capture_output=True, text=True)
        self.assertEqual(result.returncode, 87, result.stderr)
        record = json.loads(self.deploy.path.read_text())["installations"]["full"]
        self.assertEqual(record["steps"]["base tools"]["status"], "complete")
        self.assertEqual(record["steps"]["tools and plugins"]["status"], "running")
        retry = script + "\ndef no_download(*args): raise RuntimeError('unexpected second download')\nsetup.download = no_download\nsys.exit(setup.main())\n"
        result = subprocess.run([sys.executable, '-c', retry], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Resuming incomplete setup", result.stdout)
        self.assertEqual(self.output("alpha"), "alpha-1")
        record = json.loads(self.deploy.path.read_text())["installations"]["full"]
        self.assertEqual(record["status"], "complete")

    def test_failed_optional_skill_setup_is_offered_again(self):
        self.deploy.state["github_setup_prompted"] = True
        with patch("git_profiles.configure_identity"), patch("git_profiles.ask_yes", return_value=True) as ask, \
             patch.object(setup.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)):
            self.assertEqual(setup.interactive_setup({}, "linux-x86_64", self.deploy), ["AI skills"])
            self.assertNotIn("skills_setup_prompted", self.deploy.state)
        with patch("git_profiles.configure_identity"), patch("git_profiles.ask_yes", return_value=False) as ask:
            self.assertEqual(setup.interactive_setup({}, "linux-x86_64", self.deploy), [])
            ask.assert_called_once()
        self.assertTrue(self.deploy.state["skills_setup_prompted"])


if __name__ == "__main__":
    unittest.main()
