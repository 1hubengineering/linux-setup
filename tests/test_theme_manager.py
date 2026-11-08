import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("theme_manager_test", ROOT / "scripts/theme_manager.py")
themes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(themes)


class ThemeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        env = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "config"), "XDG_CACHE_HOME": str(self.root / "cache")})
        env.start()
        self.addCleanup(env.stop)

    def test_saved_local_theme_with_shell_characters_is_quoted_and_readable(self):
        path = self.root / "theme '$(touch unwanted).json"
        path.write_text('{}')
        themes.save_theme(str(path))
        hook = themes.settings_path()
        result = subprocess.run(["/bin/sh", "-c", '. "$1"; printf "%s" "$LINUX_SETUP_POSH_THEME"', "sh", str(hook)],
                                check=True, capture_output=True, text=True)
        self.assertEqual(result.stdout, str(path))
        self.assertEqual(themes.current_theme(), str(path))
        self.assertFalse((Path.cwd() / "unwanted").exists())

    def test_reset_restores_bundled_default(self):
        themes.main(["use", "paradox"])
        self.assertEqual(themes.current_theme(), "paradox")
        themes.main(["reset"])
        self.assertEqual(themes.current_theme(), str(ROOT / "config/oh-my-posh/quick-term.omp.json"))

    def test_cancel_bundled_selection_changes_nothing(self):
        themes.save_theme("paradox")
        before = themes.settings_path().read_bytes()
        with patch.object(themes, "choose", side_effect=[0, None, 5]):
            themes.menu()
        self.assertEqual(themes.settings_path().read_bytes(), before)

    def test_new_bundled_themes_resolve_locally_and_are_selectable(self):
        names = themes.bundled_themes()
        self.assertEqual(names[0], "quick-term")
        for suffix in ("ocean", "forest", "violet", "rose", "slate"):
            name = "quick-term-" + suffix
            expected = str(ROOT / f"config/oh-my-posh/{name}.omp.json")
            self.assertEqual(themes.theme_value(name), expected)
            with patch.object(themes, "choose", side_effect=[0, names.index(name), 5]):
                themes.menu()
            self.assertEqual(themes.current_theme(), expected)

    def test_theme_list_can_be_reused_offline(self):
        reply = io.StringIO(json.dumps([{"name": "paradox.omp.json", "type": "file"}, {"name": "a.minimal.omp.json", "type": "file"}]))
        with patch.object(themes.urllib.request, "urlopen", return_value=reply):
            self.assertEqual(themes.upstream_themes(), ["a.minimal", "paradox"])
        with patch.object(themes.urllib.request, "urlopen", side_effect=OSError("offline")):
            self.assertEqual(themes.upstream_themes(), ["a.minimal", "paradox"])


@unittest.skipUnless(shutil.which("oh-my-posh"), "Oh My Posh is required for live theme rendering")
class ThemeRenderingTests(unittest.TestCase):
    def render(self, config, prompt="primary", **kwargs):
        args = ["oh-my-posh", "print", prompt, "--config", str(config), "--shell", "bash", "--plain"]
        for key, value in kwargs.items():
            args += ["--" + key.replace('_', '-'), str(value)]
        return subprocess.check_output(args, text=True)

    def test_bundled_paths_show_only_parent_and_current_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "path.json"
            for name in themes.bundled_themes():
                theme = json.loads((ROOT / f"config/oh-my-posh/{name}.omp.json").read_text())
                segment = next(s for b in theme["blocks"] for s in b["segments"] if s["type"] == "path")
                # Retain the real path formatter and template, without decorative segments.
                segment = dict(segment, style="plain")
                config.write_text(json.dumps({"version": 4, "final_space": False,
                    "blocks": [{"type": "prompt", "alignment": "left", "segments": [segment]}]}))
                for path, expected in [("/", "/"), ("/home", "home"),
                    ("/home/user/projects/my-app/src", "my-app/src"),
                    ("/srv/ancestor/project with spaces/子目录", "project with spaces/子目录")]:
                    with self.subTest(theme=name, path=path):
                        shown = self.render(config, pwd=path).strip().removeprefix(" ")
                        self.assertEqual(shown, expected)

    def test_custom_prompts_have_two_lines_and_compact_transient_history(self):
        for name in [n for n in themes.bundled_themes() if n.startswith("quick-term")]:
            with self.subTest(theme=name):
                config = ROOT / f"config/oh-my-posh/{name}.omp.json"
                common = ["--data", str(ROOT / "docs/assets/prompt.data.json"), "--data-only",
                          "--config", str(config), "--shell", "bash", "--plain"]
                primary = subprocess.check_output(["oh-my-posh", "print", "primary", *common, "--terminal-width", "112"], text=True)
                self.assertEqual(len(primary.splitlines()), 2)
                self.assertIn("my-app/src", primary.splitlines()[0])
                self.assertEqual(primary.splitlines()[1], "╰─ $ ")
                transient = subprocess.check_output(["oh-my-posh", "print", "transient", *common], text=True)
                self.assertEqual(transient, "╰─ $ ")
                continuation = subprocess.check_output(["oh-my-posh", "print", "secondary", *common], text=True)
                self.assertEqual(continuation, "· ")


if __name__ == "__main__":
    unittest.main()
