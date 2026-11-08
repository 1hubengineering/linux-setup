"""Choose and save an Oh My Posh theme for this device."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import sys
import tempfile
import urllib.request
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from terminal_ui import choose

ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r"[A-Za-z0-9_.-]+")


def settings_path():
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "linux-setup-local/theme.zsh"


def current_theme():
    path = settings_path()
    if path.is_file():
        for line in path.read_text().splitlines():
            if line.startswith("export LINUX_SETUP_POSH_THEME="):
                value = shlex.split(line.split("=", 1)[1])
                if len(value) == 1:
                    return value[0]
    return os.environ.get("LINUX_SETUP_POSH_THEME", "quick-term (default)")


def theme_value(value):
    if not value or any(not char.isprintable() for char in value):
        raise ValueError("Enter a theme name, an existing JSON file, or an HTTPS URL")
    if value in ("quick-term", "iterm2"):
        return str(ROOT / "config/oh-my-posh" / (value + ".omp.json"))
    if value.startswith("https://") and urlsplit(value).hostname and not any(char.isspace() for char in value):
        return value
    path = Path(value).expanduser()
    if path.is_file():
        json.loads(path.read_text())
        return str(path.resolve())
    if NAME.fullmatch(value) and value not in (".", "..") and not value.endswith(".json"):
        return value
    raise ValueError("Use a theme name, an existing JSON file, or an HTTPS URL")


def save_theme(value):
    value = theme_value(value)
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".theme-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write("# Written by theme-manager. This selection takes precedence over the local zshenv.\n")
            stream.write("export LINUX_SETUP_POSH_THEME=" + shlex.quote(value) + "\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    print(f"Saved theme: {value}\nRun reload in Zsh, or open a new terminal, to apply it.")


def upstream_themes():
    version = json.loads((ROOT / "tools.lock.json").read_text())["tools"]["oh-my-posh"]["version"]
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "linux-setup" / ("themes-" + version + ".json")
    try:
        url = "https://api.github.com/repos/JanDeDobbeleer/oh-my-posh/contents/themes?ref=" + version
        request = urllib.request.Request(url, headers={"User-Agent": "linux-setup/1"})
        with urllib.request.urlopen(request, timeout=15) as response:
            entries = json.load(response)
        names = sorted({item["name"][:-9] for item in entries if item.get("type") == "file"
                        and item["name"].endswith(".omp.json") and NAME.fullmatch(item["name"])}, key=str.casefold)
        if not names:
            raise ValueError("No themes were returned by GitHub")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(names) + "\n")
        return names
    except (OSError, ValueError, TypeError, KeyError) as error:
        if cache.is_file():
            names = json.loads(cache.read_text())
            if isinstance(names, list) and all(isinstance(name, str) and NAME.fullmatch(name) for name in names):
                print("Using the cached upstream theme list.", file=sys.stderr)
                return names
        raise RuntimeError(f"Cannot load the upstream theme list: {error}. You can still use theme-manager use NAME.") from None


def menu():
    while True:
        action = choose("Theme manager", ["Choose a bundled theme", "Browse all upstream themes", "Use a local file or HTTPS URL",
                                         "Show current theme", "Restore the default theme", "Exit"])
        if action is None or action == 5:
            return
        try:
            if action == 0:
                choice = choose("Bundled themes", ["quick-term (default)", "iterm2", "Back"])
                if choice is not None and choice != 2:
                    save_theme(["quick-term", "iterm2"][choice])
            elif action == 1:
                names = upstream_themes()
                choice = choose("Upstream themes", names + ["Back"])
                if choice is not None and choice != len(names):
                    save_theme(names[choice])
            elif action == 2:
                value = input("Existing JSON file or HTTPS URL (blank goes back): ").strip()
                if value:
                    save_theme(value)
            elif action == 3:
                print(current_theme())
            else:
                save_theme("quick-term")
        except (RuntimeError, OSError, ValueError) as error:
            print(f"theme-manager: {error}", file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action")
    sub.add_parser("list", help="List bundled and upstream theme names (network or cached list)")
    sub.add_parser("current", help="Show the saved theme selection")
    sub.add_parser("reset", help="Restore the bundled quick-term theme")
    use = sub.add_parser("use", help="Save a theme name, local JSON path, or HTTPS URL")
    use.add_argument("theme")
    args = parser.parse_args(argv)
    if args.action == "list":
        print("quick-term (bundled)\niterm2 (bundled)")
        print("\n".join(upstream_themes()))
    elif args.action == "current":
        print(current_theme())
    elif args.action == "reset":
        save_theme("quick-term")
    elif args.action == "use":
        save_theme(args.theme)
    else:
        menu()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        sys.exit(0)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"theme-manager: {error}", file=sys.stderr)
        sys.exit(1)
