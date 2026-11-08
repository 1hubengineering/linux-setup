"""Interactive Git identity and GitHub account helpers; never store credentials."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from terminal_ui import choose, confirm


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
    return confirm(prompt, default=default)


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
    print("\nAdd a GitHub profile")
    if ask_yes("Authenticate this GitHub account now?", default=True):
        subprocess.run(["gh", "auth", "login"], check=True)
    username = ask_required("GitHub username")
    profiles = load_profiles()
    if username in profiles and not ask_yes(f"Replace saved author details for {username}?"):
        print(f"Kept the existing profile for {username}.")
        return False
    author = next(reversed(list(profiles.values())), None)
    if not author:
        author = {}
        for key, field in (("user.name", "name"), ("user.email", "email")):
            result = subprocess.run(["git", "config", "--global", "--get", key], capture_output=True, text=True)
            if result.returncode not in (0, 1):
                raise RuntimeError(f"Cannot read global Git setting {key}: {result.stderr.strip()}")
            author[field] = result.stdout.strip()
    reuse = author.get("name") and author.get("email") and ask_yes(
        f"Reuse Git author {author['name']} <{author['email']}> for {username}?", default=True)
    if reuse:
        name, email = author["name"], author["email"]
    else:
        name = ask_required("Git author name")
        email = ask_required("Git author email")
    profiles.pop(username, None)
    profiles[username] = {"name": name, "email": email}
    save_profiles(profiles)
    print(f"\nProfile created: {username}\nGit author: {name} <{email}>")
    print(f"Use git-profile use {username} inside a repository to select it.")
    return username


def add_profiles():
    while True:
        username = add_profile()
        prompt = f"Profile created: {username}. Add another GitHub profile?" if username else "Add another GitHub profile?"
        if not ask_yes(prompt):
            print("GitHub profile setup complete. Run git-profile to manage your accounts later.")
            return
        print("\nStarting a new profile. You can reuse the author details you just saved.")


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


def list_profiles():
    profiles = load_profiles()
    for username, profile in sorted(profiles.items()):
        print(f"{username}: {profile['name']} <{profile['email']}>")
    if not profiles:
        print("No profiles saved. Run git-profile add.")


def remove_profile(username, logout=False):
    profiles = load_profiles()
    if username not in profiles:
        raise RuntimeError(f"No saved profile for {username}.")
    action = "Remove the saved author profile"
    if logout:
        action += " and log out locally from GitHub CLI"
    if not ask_yes(f"{action} for {username}?"):
        return
    if logout:
        if not shutil.which("gh"):
            raise RuntimeError("GitHub CLI is missing. The saved profile was kept.")
        subprocess.run(["gh", "auth", "logout", "--hostname", "github.com", "--user", username], check=True)
    del profiles[username]
    save_profiles(profiles)
    print(f"Removed saved profile {username}. Existing repository author settings were kept.")


def menu():
    while True:
        action = choose("GitHub account manager", ["Add an account and author profile", "Switch account for this repository",
                                                  "List saved profiles", "Remove a saved profile", "Check GitHub login status", "Exit"])
        if action is None or action == 5:
            return
        try:
            if action == 0:
                add_profiles()
            elif action in (1, 3):
                usernames = sorted(load_profiles())
                if not usernames:
                    print("No profiles saved. Choose Add an account first.")
                    continue
                selected = choose("Choose a saved profile", usernames + ["Back"])
                if selected is None or selected == len(usernames):
                    continue
                if action == 1:
                    use_profile(usernames[selected])
                else:
                    mode = choose("Remove profile", ["Remove author profile only", "Remove profile and log out of GitHub CLI locally", "Back"])
                    if mode is not None and mode != 2:
                        remove_profile(usernames[selected], logout=mode == 1)
            elif action == 2:
                list_profiles()
            else:
                subprocess.run(["gh", "auth", "status"], check=True)
        except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
            print(f"git-profile: {error}", file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action")
    sub.add_parser("menu", help="Open the keyboard-driven account manager (default)")
    sub.add_parser("add", help="Add an account and its Git author details")
    sub.add_parser("list", help="List saved profiles")
    use = sub.add_parser("use", help="Select an account and set this repository's author")
    use.add_argument("username")
    remove = sub.add_parser("remove", help="Remove a saved author profile after confirmation")
    remove.add_argument("username")
    remove.add_argument("--logout", action="store_true", help="Also remove this account's local GitHub CLI login")
    args = parser.parse_args(argv)
    if args.action in (None, "menu"):
        menu()
    elif args.action == "add":
        add_profiles()
    elif args.action == "use":
        use_profile(args.username)
    elif args.action == "remove":
        remove_profile(args.username, args.logout)
    else:
        list_profiles()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)
    except (RuntimeError, OSError, subprocess.CalledProcessError, ValueError, EOFError) as error:
        print(f"git-profile: {error}", file=sys.stderr)
        sys.exit(1)
