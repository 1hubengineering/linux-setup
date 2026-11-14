# linux-setup

A Linux terminal setup with Zsh, Oh My Posh, tmux, developer tools, GitHub account
profiles, and an optional AI skill manager. Built for Ubuntu/Debian, including WSL.

[![Validate setup](https://github.com/1hubengineering/linux-setup/actions/workflows/test.yml/badge.svg)](https://github.com/1hubengineering/linux-setup/actions/workflows/test.yml)

[Install](#install) · [User guides](docs/README.md) · [Terminal previews](docs/previews.md)

![Quick-term prompt with Git context and a command reference](docs/assets/quick-term.png)

## Install

First, update and upgrade Ubuntu/Debian, then install the tools needed to clone
and run the setup. Review the package changes and restart Linux if requested.
Run these commands inside Ubuntu when using WSL:

```sh
sudo apt update && sudo apt upgrade
sudo apt install --no-install-recommends git curl ca-certificates python3
```

After that, clone and install as your normal user:

```sh
git clone https://github.com/1hubengineering/linux-setup.git ~/linux-setup
cd ~/linux-setup
./install.sh --preflight && ./install.sh --dry-run && ./install.sh
```

When installation succeeds, start Zsh:

```sh
export PATH="$HOME/.local/bin:$PATH"
exec zsh
```

Then run `doctor`. The installer prints font instructions for your
environment and the command to make Zsh your default shell. Keep the checkout:
your live configuration links to it.

Setup opens a read-only selection wizard before installing programs or changing
configuration. Choose programs, agents, scope, integrations, and Git/GitHub actions,
then review and apply the plan. Selected missing base tools install without sudo
on Ubuntu/Debian; existing configuration is backed up. Move through menus with **arrow keys**, toggle multiple
choices with **Space**, and press **Enter** to confirm. **Esc** goes back.

Rerun `./install.sh` after a failed or interrupted installation. Completed tools
are kept. The wizard skips installed versions; `--no-wizard` retains the earlier
flow with confirmation for available pinned updates. See
[rerun and recovery](docs/recovery.md).

[Installation details and supported systems](docs/installation.md) ·
[Fix unreadable icons or set the default shell](docs/fonts-and-shell.md)

## Start using it

| I want to… | Run | Guide |
| --- | --- | --- |
| Update my terminal setup | `update` | [Updates](docs/installation.md#update-an-existing-installation) |
| Change my prompt theme | `theme` | [Themes](docs/themes.md) |
| Add, switch, or remove a GitHub profile | `github` | [GitHub accounts](docs/github-accounts.md) |
| Install or remove AI skills | `skills` | [AI skills](docs/skills.md) |
| Find a shortcut | **Alt+X** or `devcommands` | [Commands](docs/commands.md) |
| Check my setup | `doctor` | [Troubleshooting](docs/troubleshooting.md) |
| See font and shell instructions again | `guide` | [Fonts and shell](docs/fonts-and-shell.md) |

[All user guides](docs/README.md) cover project checks, browser testing, databases,
updates, and uninstalling. See [included tools](docs/tools.md) for the full tool
list and [development](docs/development.md) to contribute.

Report problems through [GitHub Issues](https://github.com/1hubengineering/linux-setup/issues)
with your distribution, architecture, and redacted error output.
[Third-party notices](NOTICE.md).

See [developer tools and shell switching](docs/developer-tools.md) for Python/uv,
Codex/Claude authentication, MCP servers, project workflows, and Bash support.

Interactive installation now starts with a [selection wizard](docs/setup-wizard.md):
choose programs, agents, scope, integrations, and Git/GitHub actions before changes.
Use `--no-wizard` for the legacy batch flow.
