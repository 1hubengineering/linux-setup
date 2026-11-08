import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import next_steps


class NextStepsTests(unittest.TestCase):
    def test_wsl_prints_powershell_and_actual_rootless_shell_commands(self):
        with patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}, clear=True), \
             patch("sys.stdout", new_callable=io.StringIO) as output:
            next_steps.print_guide("/home/example/.local/bin/zsh")
        guide = output.getvalue()
        self.assertIn("Windows PowerShell", guide)
        self.assertIn("winget install --id JanDeDobbeleer.OhMyPosh", guide)
        self.assertIn("oh-my-posh font install meslo", guide)
        self.assertIn("chsh -s /home/example/.local/bin/zsh", guide)
        self.assertIn("sudo tee -a /etc/shells", guide)

    def test_local_linux_prints_font_cache_instructions(self):
        with patch.object(next_steps, "environment", return_value="linux"), \
             patch("sys.stdout", new_callable=io.StringIO) as output:
            next_steps.print_guide("/bin/zsh")
        self.assertIn("fc-cache -f", output.getvalue())
        self.assertNotIn("winget", output.getvalue())

    def test_ssh_takes_precedence_over_wsl_host_detection(self):
        with patch.dict(os.environ, {"SSH_CONNECTION": "client server", "WSL_DISTRO_NAME": "Ubuntu"}, clear=True):
            self.assertEqual(next_steps.environment(), "ssh")


if __name__ == "__main__":
    unittest.main()
