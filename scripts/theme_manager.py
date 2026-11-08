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


def bundled_themes():
    names = sorted(path.name[:-9] for path in (ROOT / "config/oh-my-posh").glob("*.omp.json") if not path.is_symlink())
    return ["quick-term"] + [name for name in names if name != "quick-term"]


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
    bundled = ROOT / "config/oh-my-posh" / (value + ".omp.json")
    if value in bundled_themes() or (NAME.fullmatch(value) and bundled.is_symlink()):
        return str(bundled.resolve())
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
    label = Path(value).name.removesuffix(".omp.json") if not value.startswith("https://") else value
    print(f"\nTheme changed to {label}.\nRun reload to see it now, or close and reopen your terminal.", flush=True)


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
                print("Showing the theme list saved from your last visit.", file=sys.stderr)
                return names
        raise RuntimeError(f"Cannot load the online theme list: {error}. You can still use theme use NAME.") from None


def menu():
    while True:
        action = choose("Theme manager", ["Choose an included theme", "Browse more themes online", "Choose a theme file or web link",
                                         "Show current theme", "Restore the default theme", "Exit"])
        if action is None or action == 5:
            return
        try:
            if action == 0:
                names = bundled_themes()
                choice = choose("Included themes", [name + (" (default)" if name == "quick-term" else "") for name in names] + ["Back"])
                if choice is not None and choice != len(names):
                    save_theme(names[choice])
                    return
            elif action == 1:
                names = upstream_themes()
                choice = choose("Online themes", names + ["Back"])
                if choice is not None and choice != len(names):
                    save_theme(names[choice])
                    return
            elif action == 2:
                value = input("Theme file path or https:// web link (leave blank to go back): ").strip()
                if value:
                    save_theme(value)
                    return
            elif action == 3:
                print("Current theme: " + current_theme())
                return
            else:
                save_theme("quick-term")
                return
        except (RuntimeError, OSError, ValueError) as error:
            print(f"Theme was not changed: {error}", file=sys.stderr)
            if sys.stdin.isatty() and sys.stdout.isatty():
                input("Press Enter to return to the menu.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action")
    sub.add_parser("list", help="List included themes and the online theme list")
    sub.add_parser("current", help="Show the saved theme selection")
    sub.add_parser("reset", help="Restore the included quick-term theme")
    use = sub.add_parser("use", help="Save a theme name, local JSON path, or HTTPS URL")
    use.add_argument("theme")
    args = parser.parse_args(argv)
    if args.action == "list":
        print("\n".join(name + " (included)" for name in bundled_themes()))
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
