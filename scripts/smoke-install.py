#!/usr/bin/env python3
"""Exercise real install/uninstall/reinstall in a disposable home (network required)."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-from", type=Path, help="Reuse this setup download directory; copies only regular archive files")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="linux-setup-smoke-") as temporary:
        root = Path(temporary)
        environment = dict(os.environ)
        for key in ("VP_HOME", "VP_BIN_DIR", "UV_INSTALL_DIR", "ZDOTDIR", "_LINUX_SETUP_USER_ZDOTDIR", "GIT_CONFIG_GLOBAL"):
            environment.pop(key, None)
        environment.update(HOME=str(root), PATH=str(root / ".local/bin") + ":/usr/bin:/bin", CI="1",
                           GIT_CONFIG_GLOBAL=str(root / ".gitconfig"), GIT_CONFIG_NOSYSTEM="1")
        for kind, suffix in (("CONFIG", ".config"), ("DATA", ".local/share"), ("STATE", ".local/state"), ("CACHE", ".cache")):
            environment[f"XDG_{kind}_HOME"] = str(root / suffix)
        if args.cache_from:
            destination = root / ".cache/linux-setup/downloads"
            destination.mkdir(parents=True)
            for path in args.cache_from.iterdir():
                if path.is_file() and not path.is_symlink():
                    shutil.copy2(path, destination / path.name)
        def run(*command):
            print("SMOKE:", " ".join(map(str, command)), flush=True)
            subprocess.run(list(map(str, command)), cwd=ROOT, env=environment, check=True)
        run(ROOT / "install.sh", "--skip-mcp")
        # Rerunning must leave artifacts, backups, and original link records intact.
        manifest = root / ".local/state/linux-setup/deployment.json"
        first = json.loads(manifest.read_text())
        repeated = subprocess.run([str(ROOT / "install.sh"), "--skip-mcp"], cwd=ROOT, env=environment,
                                  check=True, capture_output=True, text=True)
        print(repeated.stdout, end="", flush=True)
        assert "already installed" in repeated.stdout.lower(), "Rerun did not explain reused installation"
        assert "Downloading " not in repeated.stdout, "Rerun downloaded a completed tool"
        second = json.loads(manifest.read_text())
        assert first["links"] == second["links"], "Rerun changed link ownership or original backups"
        for name, item in first["programs"].items():
            assert item.get("fingerprints") == second["programs"][name].get("fingerprints"), "Rerun changed " + name
        assert second["installations"]["full"]["status"] == "complete", "Rerun did not finish"
        run(ROOT / "install.sh", "--check")
        run("dev-check", "--help")
        run("dev-browser", "--help")
        run(ROOT / "uninstall.sh", "--keep-tools", "--yes")
        for helper in ("dev-check", "dev-browser"):
            assert not (root / ".local/bin" / helper).is_symlink(), "Configuration uninstall left " + helper
        # Retained rootless Zsh must load modules without the setup's .zshenv.
        run("zsh", "-c", "zmodload zsh/parameter && autoload -Uz compinit && compinit -i -D")
        run("uv", "--version")
        run("vp", "--version")
        run(ROOT / "install.sh", "--config-only", "--skip-mcp")
        run("dev-check", "--help")
        run("dev-browser", "--help")
        cache = root / ".cache/bat"
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "smoke-cache").write_text("disposable test cache")
        run(ROOT / "uninstall.sh", "--remove", "fd", "--cache", "bat", "--yes")
        assert not (root / ".local/bin/fd").exists(), "Selected fd executable remains"
        assert not cache.exists(), "Selected bat cache remains"
        run("bat", "--version")
        run(ROOT / "uninstall.sh", "--all-tools", "--yes")
        assert not (root / ".local/bin/bat").exists(), "All-tools removal left bat"
        run(ROOT / "install.sh", "--skip-mcp")
        run(ROOT / "install.sh", "--check")
        print("SMOKE PASSED: fresh install, repeat install, keep-tools, selective removal/cache cleanup, all-tools removal, reinstall", flush=True)


if __name__ == "__main__":
    main()
