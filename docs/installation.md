# Installation and migration

[Documentation](README.md) · [Project overview](../README.md)

`linux-setup` installs a repeatable Linux terminal configuration and a pinned set
of command-line tools. It links configuration to this checkout, so keep the
checkout in a persistent location.

## Supported systems

Ubuntu/Debian on x86_64 is the primary target; development testing used Ubuntu
26.04 x86_64. ARM64 release mappings are included but still need equivalent
hardware validation. Ubuntu/Debian inside WSL uses the same Linux installation
path. Other glibc distributions need their own base packages installed first and
are not yet integration-tested. Native Windows/PowerShell, macOS, and musl Linux
are outside this release's supported targets.

Pinned binaries still depend on compatible host libraries. Pinning tools does
not freeze the operating system or guarantee compatibility with every older
distribution release.

## Before starting

Required bootstrap components are Bash, Python 3.9 or newer, a working HTTPS
connection, and trusted certificate authorities. Git is needed to clone the
repository; a downloaded ZIP is another way to obtain the files. On Ubuntu/Debian,
rootless base-tool installation also requires `apt-get`, `dpkg-deb`, and populated
package indexes.

Update and upgrade Ubuntu/Debian **before cloning**. Review the package changes
and restart if Linux requests it. Run this inside Ubuntu when using WSL:

```sh
sudo apt update && sudo apt upgrade
sudo apt install --no-install-recommends git curl ca-certificates python3
```

Then clone and install as your normal user:

```sh
git clone https://github.com/1hubengineering/linux-setup.git ~/linux-setup
cd ~/linux-setup
./install.sh --preflight && ./install.sh --dry-run && ./install.sh
```

After installation succeeds:

```sh
export PATH="$HOME/.local/bin:$PATH"
exec zsh
doctor
```

The preflight checks prerequisites before installation. Its GitHub homepage probe
is advisory: a failure may not reflect access to release downloads, which are
checked during installation. If installation fails, do not run `exec zsh` until
the error has been resolved and installation succeeds. The dry run describes the
installation without applying it. Downloaded artifacts are verified against the
SHA-256 values in `tools.lock.json`; repeat installs reuse verified downloads.

If Ubuntu/Debian bootstrap prerequisites or current package indexes are missing:

```sh
./install.sh --install-prerequisites
```

This explicit option displays the administrative package operations before
requesting authentication. It prepares Python, Git, curl, certificate trust, and
APT indexes, then continues the normal installation. To preview both stages, add
`--dry-run`; `--yes` explicitly confirms the administrative prerequisite commands
for automation. Normal tool installation does not need sudo: missing base programs
are extracted into your user directory. On restricted devices, ask the system
administrator to provide prerequisites instead.

On other compatible glibc Linux distributions, install Bash, Python 3.9+, Git,
curl, CA certificates, Zsh, tmux, `file`, `lsof`, and the PostgreSQL client (`psql`)
through the distribution's package manager before running this installer.

Do not run the entire installer with `sudo`; it is intended to configure the
current user's home directory.

## What gets installed

The [included tools reference](tools.md) lists the included programs.
Already available programs are reused, including external installations.
Fresh Vite+/uv installations use the lockfile versions.

Zsh is installed automatically when it is missing during a normal `./install.sh`
run on Ubuntu/Debian. Its packages and runtime files stay in your user directory,
with an executable entry point at `~/.local/bin/zsh`; no sudo or login-shell change
is needed. An existing Zsh is reused. `--config-only` deliberately skips all tool
installation, including Zsh. At completion, the installer prints an `exec` command
with the full Zsh path so it also works before your current shell has added
`~/.local/bin` to `PATH`.

On an interactive normal installation, the installer asks for a Git author name
and email only when the corresponding global value is missing. It then offers
GitHub CLI installation and account setup on the first interactive run. Existing
values and an existing `gh` installation are preserved. Non-interactive runs,
preflight, dry runs, and configuration-only runs do not prompt. You can revisit
the account flow with `./install.sh --github-setup`, or install just the optional
CLI with `./install.sh --install-gh`. The GitHub CLI download is pinned and
checksum-verified like the other managed tools. See [GitHub accounts](github-accounts.md)
for sharing author details, adding another profile, switching, and removal.

The first interactive installation also offers the optional AI skill manager.
Choose Codex or Claude Code, one or more work areas, and whether skills should apply to all projects or one.
Use arrows to move, Space to toggle choices, and Enter to confirm. Esc goes back. You
can skip this step and run `skills` later. See
[AI skills](skills.md) for sources and removal.

The PostgreSQL dependency is the `psql` client only. Installing it does not create
a database cluster or start a server. Your applications retain responsibility for
their Node/Python versions and dependency lockfiles.

The ownership manifest records managed programs, configuration links, backups,
and integrations so the [uninstaller](uninstall.md) can separate setup-owned
resources from pre-existing installations.

Default locations, respecting the corresponding XDG variables:

| Content | Default location |
| --- | --- |
| Configuration checkout link | `~/.config/linux-setup` |
| Private machine additions | `~/.config/linux-setup-local/` |
| Executable entry points | `~/.local/bin/` |
| Managed programs and plugins | `~/.local/share/linux-setup/` |
| Downloads and setup caches | `~/.cache/linux-setup/` |
| Manifest, backups, recovery records | `~/.local/state/linux-setup/` |
| Zsh history | `~/.local/state/zsh/history` |

The installer backs up configurations it replaces. The Git include applies this
project's diff settings without copying your Git identity into the repository.
If Codex is present and the `oh-my-posh` MCP registration is absent, the normal
install adds the endpoint. An existing registration is preserved. Use `--skip-mcp`
to leave that integration alone.

## Migrating from dev-setup

Run the current installer from the renamed or freshly cloned `linux-setup`
checkout. It recognizes the earlier `dev-setup` directories and manifest,
preserves original backups and personal additions, and updates managed paths.
Compatibility paths may remain so older wrappers and customizations continue to
resolve. Do not delete those paths by hand while retained tools still use them.

`LINUX_SETUP_DIR` is the canonical environment variable; `DEV_SETUP_DIR` remains
available for existing scripts. The familiar `dev-doctor`, `devsetup`, `dev-db`,
and `dev-ports` commands remain usable. New branding also provides `doctor`
and `linuxsetup`.

Migration is repeatable after interruption. If both old and new locations contain
different data, the installer reports the conflict instead of overwriting it.
Resolve the reported paths and rerun; never remove backups or recovery records
just to clear a conflict. Earlier manifests have incomplete program ownership,
so uninstallation keeps uncertain resources and reports them for review.

To move a checkout later, move/copy it to its persistent destination and rerun
`./install.sh` there to repair managed links. Open a new shell afterward.

## Update an existing installation

From any directory in your configured Zsh terminal:

```sh
update
```

The alias locates this checkout, runs `git pull --ff-only`, then runs the updated
installer. Your working directory stays the same. Other shells can run
`linux-setup-update`. Git conflicts, diverged history, or a failed pull stop the
command before installation. Resolve the Git problem and retry. A failed
installation can also be retried with `update`.

To get this shortcut on an older installation, update once manually and reload:

```sh
cd ~/linux-setup
git pull --ff-only
./install.sh
exec zsh
```

Completed tools report that they are already installed. If a managed tool or
plugin has a new pinned version, an interactive run asks before updating it;
non-interactive runs keep the installed version. Rerunning also retries incomplete
steps after a failure or interruption. See [rerun and recovery](recovery.md).

On success, run `exec zsh`. For configuration changes without tool downloads,
use `./install.sh --config-only --skip-mcp`. Existing Vite+ and uv versions are
preserved; upgrade those managers through their own supported commands.

## Default shell

At the end of setup, the installer prints your actual Zsh path, any required
registration in `/etc/shells`, and the `chsh -s` command. Follow the
[default-shell guide](fonts-and-shell.md#make-zsh-your-default-shell), or run
`guide` to show those instructions again. The installer does not
change your login shell automatically.

## Optional terminal features

The completion guide detects WSL, SSH, or local Linux and explains where to
install a Nerd Font. [Font instructions](fonts-and-shell.md#fix-missing-prompt-icons)
include PowerShell commands for Windows and shell commands for Linux, followed
by selecting the installed font in your terminal settings.

Extra Yazi previews use optional tools:

```sh
sudo apt install ffmpeg poppler-utils 7zip
```

These provide video, PDF, and archive previews. Packages installed manually with
this command belong to the system package manager; the setup uninstaller does
not claim or remove them. Basic file navigation, search, JSON previews, and fuzzy
selection use the tools already included in the setup.

For download errors, missing libraries, or completion problems, see
[troubleshooting](troubleshooting.md).
