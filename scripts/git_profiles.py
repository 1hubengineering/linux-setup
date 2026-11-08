"""Interactive Git identity and GitHub account helpers; never store credentials."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def profiles_path():
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "linux-setup-local/git-profiles.json"


def load_profiles():
    path = profiles_path()
    return json.loads(path.read_text()) if path.exists() else {}


def save_profiles(profiles):
    path = profiles_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".git-profiles-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(profiles, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def ask_yes(prompt, default=False):
    suffix = " [Y/n] " if default else " [y/N] "
    while True:
        answer = input(prompt + suffix).strip().lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer yes or no.")


def ask_required(prompt, default=""):
    while True:
        answer = input(prompt + (f" [{default}]" if default else "") + ": ").strip() or default
        if answer:
            return answer
        print("A value is required.")


def configure_identity():
    for key, label in (("user.name", "Git author name"), ("user.email", "Git author email")):
        result = subprocess.run(["git", "config", "--global", "--get", key], capture_output=True, text=True)
        if result.returncode not in (0, 1):
            raise RuntimeError(f"Cannot read global Git setting {key}: {result.stderr.strip()}")
        if not result.stdout.strip():
            value = ask_required(label)
            subprocess.run(["git", "config", "--global", key, value], check=True)


def add_profile():
    if not shutil.which("gh"):
        raise RuntimeError("GitHub CLI is missing. Run ./install.sh --install-gh first.")
    if ask_yes("Authenticate another GitHub account now?", default=True):
        subprocess.run(["gh", "auth", "login"], check=True)
    username = ask_required("GitHub username")
    profiles = load_profiles()
    if username in profiles and not ask_yes(f"Replace saved author details for {username}?"):
        return
    name = ask_required("Git author name")
    email = ask_required("Git author email")
    profiles[username] = {"name": name, "email": email}
    save_profiles(profiles)
    print(f"Saved {username}. Use git-profile use {username} inside a repository.")


def use_profile(username):
    profiles = load_profiles()
    if username not in profiles:
        raise RuntimeError(f"No saved profile for {username}. Run git-profile add first.")
    subprocess.run(["git", "rev-parse", "--git-dir"], check=True, stdout=subprocess.DEVNULL)
    if not shutil.which("gh"):
        raise RuntimeError("GitHub CLI is missing. Run ./install.sh --install-gh first.")
    subprocess.run(["gh", "auth", "switch", "--hostname", "github.com", "--user", username], check=True)
    for key, value in (("user.name", profiles[username]["name"]), ("user.email", profiles[username]["email"])):
        subprocess.run(["git", "config", "--local", key, value], check=True)
    print(f"Selected {username}: repository author updated; GitHub CLI active account changed for github.com.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("add", help="Add an account and its Git author details")
    sub.add_parser("list", help="List saved profiles")
    use = sub.add_parser("use", help="Select an account and set this repository's author")
    use.add_argument("username")
    args = parser.parse_args()
    if args.action == "add":
        add_profile()
    elif args.action == "use":
        use_profile(args.username)
    else:
        profiles = load_profiles()
        for username, profile in sorted(profiles.items()):
            print(f"{username}: {profile['name']} <{profile['email']}>")
        if not profiles:
            print("No profiles saved. Run git-profile add.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, subprocess.CalledProcessError, ValueError, EOFError) as error:
        print(f"git-profile: {error}", file=sys.stderr)
        sys.exit(1)
