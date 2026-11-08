# Fonts and the default shell

[User guides](README.md) · [Installation](installation.md) · [Themes](themes.md)

Run `guide` at any time to see instructions for your environment.
These steps are optional; they are printed at the end of installation too.

## Fix missing prompt icons

Boxes, question marks, and broken icons usually mean the terminal needs a Nerd
Font. Install the font on the computer displaying the terminal, then select it
in that terminal's settings. [Oh My Posh's font guide](https://ohmyposh.dev/docs/installation/fonts)
explains why WSL and remote sessions need fonts on the client.

### WSL: run these commands in Windows PowerShell

If Oh My Posh is not installed on Windows, install it with:

```powershell
winget install --id JanDeDobbeleer.OhMyPosh --exact --source winget
```

Close and reopen PowerShell so the new command is on PATH, then install Meslo:

```powershell
oh-my-posh font install meslo
```

The Windows copy is used here to install the font. The prompt in Ubuntu still
uses the Linux installation. You do not need to configure a PowerShell prompt.

In Windows Terminal, press **Ctrl+,**, choose the Ubuntu profile, then open
**Appearance > Font face**. Choose **MesloLGM Nerd Font** or the installed Meslo
Nerd Font variant. Save and reopen the tab. To apply the same font to all
profiles, use the Defaults profile. See the
[Windows Terminal appearance settings](https://learn.microsoft.com/en-us/windows/terminal/customize-settings/profile-appearance).

If WinGet is unavailable, download Meslo from [Nerd Fonts](https://www.nerdfonts.com/font-downloads),
extract the archive in Windows, and use Install on its `.ttf` files. Select the
font in Windows Terminal afterward.

### A local Linux desktop

Run as your normal user after installing linux-setup:

```sh
oh-my-posh font install meslo
fc-cache -f
```

If `fc-cache` is missing, Ubuntu/Debian provides it through `sudo apt install
fontconfig`. Then open your terminal emulator's preferences and select the
installed Meslo Nerd Font. Restart the terminal if the font list has not refreshed.

### SSH, containers, and VS Code

For SSH and containers, install the font on your desktop client using the
Windows or Linux instructions above. In VS Code, set **Terminal > Integrated:
Font Family** to the installed font's family name, such as `MesloLGM Nerd Font`.
Installing fonts only on the remote server will not change the client's display.

## Make Zsh your default shell

The installer prints commands using your actual Zsh path. To find that path:

```sh
export PATH="$HOME/.local/bin:$PATH"
zsh_path="$(command -v zsh)"
printf '%s\n' "$zsh_path"
```

If this prints no path, rerun a full `./install.sh` before continuing. Check
whether the printed path is registered:

```sh
grep -Fx -- "$zsh_path" /etc/shells
```

If it is absent, register it with administrator access:

```sh
printf '%s\n' "$zsh_path" | sudo tee -a /etc/shells
```

Then change your account's login shell:

```sh
chsh -s "$zsh_path"
```

Authenticate if asked. Log out and back in, or close and reopen the WSL session.
`exec zsh` switches the current terminal immediately; it does not change the
account's login shell. A Windows Terminal profile configured to run Bash
explicitly must also be adjusted to launch the distribution's default shell.

If administrator access is unavailable, keep using `exec zsh`. A user-installed
Zsh at `~/.local/bin/zsh` must remain installed while it is the account's login
shell. [Uninstall](uninstall.md) protects this path until a replacement is selected.
See [`chsh` in the Ubuntu manual](https://manpages.ubuntu.com/manpages/noble/man1/chsh.1.html).
