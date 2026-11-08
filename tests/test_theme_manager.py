import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
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

    def test_theme_list_can_be_reused_offline(self):
        reply = io.StringIO(json.dumps([{"name": "paradox.omp.json", "type": "file"}, {"name": "a.minimal.omp.json", "type": "file"}]))
        with patch.object(themes.urllib.request, "urlopen", return_value=reply):
            self.assertEqual(themes.upstream_themes(), ["a.minimal", "paradox"])
        with patch.object(themes.urllib.request, "urlopen", side_effect=OSError("offline")):
            self.assertEqual(themes.upstream_themes(), ["a.minimal", "paradox"])


if __name__ == "__main__":
    unittest.main()
