# Find and use your commands

[User guides](README.md) · [Terminal shortcuts](terminal.md)

Press **Alt+X** or run `devcommands` to search custom commands by name or
description. Enter places the selected command in your editable prompt. Review
its arguments before running it. Esc cancels. If Alt+X is intercepted by your
terminal, press Escape followed by x.

```sh
devcommands docker                 # Open the picker with a search
devhelp pnpm                       # Print matching command descriptions
```

## Managers and setup

| Command | Use it for | Guide |
| --- | --- | --- |
| `theme-manager` | Browse, save, or reset a prompt theme | [Themes](themes.md) |
| `git-profile` | Add, switch, list, and remove GitHub profiles | [GitHub accounts](github-accounts.md) |
| `skill-manager` | Install or remove agent skills by work area | [AI skills](skills.md) |
| `linux-setup-guide` | Show font and default-shell instructions | [Fonts and shell](fonts-and-shell.md) |
| `linux-doctor` / `dev-doctor` | Check tools and shell integrations | [Troubleshooting](troubleshooting.md) |
| `./install.sh` | Install or refresh this setup from its checkout | [Installation](installation.md) |
| `./uninstall.sh` | Restore configuration and choose tools to remove | [Uninstall](uninstall.md) |

## Work in a project

| Command | Use it for | Guide |
| --- | --- | --- |
| `dev-check [DIR]` | Check local project prerequisites | [Developer workflow](developer-workflow.md#check-a-checkout) |
| `dev-browser doctor` | Check browser-testing prerequisites | [Browser testing](developer-workflow.md#prepare-browser-tests) |
| `work [DIR]` / `dev-session [DIR]` | Open a named tmux session for a project | [Sessions](terminal.md#tmux-and-project-sessions) |
| `lip [PORT]` / `dev-ports [PORT]` | Inspect TCP listeners | [Ports](terminal.md#ports-and-local-servers) |
| `kip PORT` | Confirm before stopping a port's processes | [Ports](terminal.md#ports-and-local-servers) |
| `serve [PORT] [DIR]` | Serve files on localhost | [Local server](terminal.md#ports-and-local-servers) |
| `db` / `dev-db` | Open the PostgreSQL manager | [Databases](databases.md) |
| `db --connections` | List discovered PostgreSQL targets | [Databases](databases.md) |

Shell shortcuts such as `work`, `lip`, `kip`, `serve`, and `db` are loaded in Zsh.
The corresponding `dev-*` executables can also run from other shells. Use
`--help` on the executable commands for their options. The skill manager opens
its menu directly. Shortcuts for Docker, Kubernetes, Terraform, and other tools
do not install those tools; consult [included tools](tools.md).
