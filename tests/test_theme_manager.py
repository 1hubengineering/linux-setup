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
        for suffix in ("wholespace", "unicorn", "tiwahu", "spaceship", "night-owl", "kali"):
            name = "setup-" + suffix
            expected = str(ROOT / f"config/oh-my-posh/{name}.omp.json")
            self.assertEqual(themes.theme_value(name), expected)
            with patch.object(themes, "choose", side_effect=[0, names.index(name), 5]):
                themes.menu()
            self.assertEqual(themes.current_theme(), expected)

    def test_selection_closes_menu_and_leaves_confirmation_visible(self):
        names = themes.bundled_themes()
        with patch.object(themes, "choose", side_effect=[0, names.index("setup-kali")]) as choose, \
             patch("sys.stdout", new_callable=io.StringIO) as output:
            themes.menu()
        self.assertEqual(choose.call_count, 2)
        self.assertIn("Theme changed to setup-kali", output.getvalue())
        self.assertIn("Run reload", output.getvalue())
        self.assertIn("close and reopen your terminal", output.getvalue())

    def test_reset_closes_menu_and_confirms_default_theme(self):
        with patch.object(themes, "choose", side_effect=[4]) as choose, \
             patch("sys.stdout", new_callable=io.StringIO) as output:
            themes.menu()
        choose.assert_called_once()
        self.assertIn("Theme changed to quick-term", output.getvalue())

    def test_retired_palettes_remain_readable_but_are_not_offered_as_layouts(self):
        for suffix in ("ocean", "forest", "violet", "rose", "slate"):
            name = "quick-term-" + suffix
            self.assertNotIn(name, themes.bundled_themes())
            path = ROOT / f"config/oh-my-posh/{name}.omp.json"
            self.assertTrue(path.is_file())
            self.assertEqual(json.loads(path.read_text()), json.loads((path.parent / "quick-term.omp.json").read_text()))
            self.assertEqual(themes.theme_value(name), str(path.resolve()))

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

    def test_clean_detailed_preserves_upstream_segments_with_blank_row_spacing(self):
        config = ROOT / "config/oh-my-posh/clean-detailed.omp.json"
        theme = json.loads(config.read_text())
        self.assertEqual([[s["type"] for s in block["segments"]] for block in theme["blocks"]],
                         [["os", "shell", "sysinfo", "executiontime"], ["git"], ["text", "time", "root", "path"], ["status"]])
        self.assertEqual(theme["blocks"][1]["alignment"], "right")
        self.assertEqual(self.render(config, prompt="transient"), "\ue285 ")
        primary = self.render(config, pwd="/srv/project with spaces/子目录")
        lines = primary.splitlines()
        self.assertEqual(len(lines), 5)
        self.assertFalse(lines[1].strip())
        self.assertFalse(lines[3].strip())
        self.assertIn("MEM:", primary)
        self.assertIn("子目录", primary)
        self.assertIn("╭─", primary)
        self.assertIn("╰─", primary)
        self.assertNotIn("unable to", primary.lower())

    def test_existing_themes_keep_distinct_original_path_styles(self):
        expected = {"quick-term": "agnoster_short", "iterm2": "full", "setup-wholespace": "agnoster_full",
                    "setup-unicorn": "full", "setup-tiwahu": "mixed", "setup-spaceship": "folder"}
        for name, style in expected.items():
            theme = json.loads((ROOT / f"config/oh-my-posh/{name}.omp.json").read_text())
            segment = next(s for b in theme["blocks"] for s in b["segments"] if s["type"] == "path")
            self.assertEqual(segment.get("options", segment.get("properties", {})).get("style"), style, name)

    def test_custom_prompts_have_two_lines_and_compact_transient_history(self):
        markers = {"quick-term": "╰─ $ ", "setup-wholespace": " ", "setup-unicorn": "🦄 ",
                   "setup-tiwahu": "% ", "setup-spaceship": "❯ ", "setup-night-owl": "╰─  ", "setup-kali": "└─$ "}
        for name, marker in markers.items():
            with self.subTest(theme=name):
                config = ROOT / f"config/oh-my-posh/{name}.omp.json"
                common = ["--data", str(ROOT / "docs/assets/prompt.data.json"), "--data-only",
                          "--config", str(config), "--shell", "bash", "--plain"]
                primary = subprocess.check_output(["oh-my-posh", "print", "primary", *common, "--terminal-width", "112"], text=True)
                self.assertEqual(len(primary.splitlines()), 2)
                self.assertTrue(primary.splitlines()[0])
                self.assertTrue(primary.splitlines()[1].endswith(marker))
                self.assertFalse(primary.splitlines()[1].endswith("  "))
                transient = subprocess.check_output(["oh-my-posh", "print", "transient", *common], text=True)
                self.assertEqual(transient, marker)
                continuation = subprocess.check_output(["oh-my-posh", "print", "secondary", *common], text=True)
                self.assertEqual(continuation, "· ")


if __name__ == "__main__":
    unittest.main()
