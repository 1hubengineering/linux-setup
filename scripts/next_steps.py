"""Print environment-specific font and login-shell instructions; make no changes."""
import os
from pathlib import Path
import shlex
import shutil


def environment():
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return "ssh"
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return "wsl"
    try:
        if "microsoft" in Path("/proc/sys/kernel/osrelease").read_text().lower():
            return "wsl"
    except OSError:
        pass
    return "linux"


def print_guide(zsh=None):
    target = environment()
    print("\nSet up prompt icons")
    if target == "wsl":
        print("WSL detected. Install the font on Windows, where your terminal renders it.")
        print("Run in Windows PowerShell (skip this if Windows already has Oh My Posh):")
        print("  winget install --id JanDeDobbeleer.OhMyPosh --exact --source winget")
        print("Reopen PowerShell after installing, then run there:")
        print("  oh-my-posh font install meslo")
        print("In Windows Terminal: Settings (Ctrl+,) > your Ubuntu/Linux profile > Appearance > Font face.")
        print("Select MesloLGM Nerd Font (or the installed Meslo Nerd Font variant), save, and reopen the tab.")
    elif target == "ssh":
        print("SSH detected. Install and select a Nerd Font on the computer running your terminal.")
        print("Run linux-setup-guide locally on a Linux client, or follow docs/fonts-and-shell.md for Windows.")
    else:
        print("Run in this Linux desktop terminal:")
        print("  oh-my-posh font install meslo")
        print("  fc-cache -f  # If fontconfig is installed")
        print("Select MesloLGM Nerd Font (or the installed Meslo Nerd Font variant) in your terminal's font settings.")
        print("For a remote, container, or headless session, configure the font on the computer displaying the terminal.")
    print("Details: https://github.com/1hubengineering/linux-setup/blob/main/docs/fonts-and-shell.md")
    zsh = zsh or shutil.which("zsh")
    if zsh:
        path = shlex.quote(str(Path(zsh).absolute()))
        print("\nMake Zsh your default login shell (optional)")
        try:
            registered = str(Path(zsh).absolute()) in Path("/etc/shells").read_text().splitlines()
        except OSError:
            registered = False
        if not registered:
            print("This Zsh path must be registered first; the following command needs administrator access:")
            print(f"  printf '%s\\n' {path} | sudo tee -a /etc/shells")
        print(f"  chsh -s {path}")
        print("Log out and back in, or reopen your WSL session. A terminal profile with an explicit Bash command must also be updated.")
    print("\nEveryday commands")
    print("  update              Pull setup changes and rerun installation from any directory")
    print("  theme-manager       Change the prompt theme; run reload afterward")
    print("  git-profile         Add, switch, or remove GitHub account profiles")
    print("  skill-manager       Add or remove AI skills; choose multiple work areas")
    print("  linux-doctor        Check the terminal setup")
    print("  linux-setup-guide   Show these font and shell instructions again")
    print("Guides: https://github.com/1hubengineering/linux-setup/blob/main/docs/README.md")


if __name__ == "__main__":
    print_guide()
