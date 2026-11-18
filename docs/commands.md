# Find and use your commands

[User guides](README.md) · [Terminal shortcuts](terminal.md)

Run `mycommands` in Bash or Zsh for a table of active shortcuts. Add a search
term to match names, descriptions, or definitions. Piping the list produces four
tab-separated fields per row (shortcut, type, description, and full command).

Press **Alt+X** to search the same catalog interactively. The preview shows the
full shell definition with bat syntax highlighting. Shift+Up/Down scrolls it,
Ctrl+/ hides or shows it, and Enter puts the selection on your command line for
editing. Esc cancels. If your terminal intercepts Alt+X, press Escape followed by x.

```sh
mycommands docker                  # List Docker shortcuts
devcommands docker                 # Open the Zsh picker with an initial search
```

## Managers and setup

The short names below work in the configured Bash and Zsh terminals. For scripts or other
shells, use these full command names:

| Short name | Full command |
| --- | --- |
| `theme` | `theme-manager` |
| `github` | `git-profile` |
| `skills` | `skill-manager` |
| `doctor` | `linux-doctor` |
| `guide` | `linux-setup-guide` |

Run `reload` after updating to load new shortcuts.

| Command | Use it for | Guide |
| --- | --- | --- |
| `setup-pull` / `linux-setup-update --pull-only` | Pull setup changes from the checkout's tracking branch | [Updates](installation.md#update-an-existing-installation) |
| `update` / `linux-setup-update` | Pull the latest setup and rerun installation from any directory | [Updates](installation.md#update-an-existing-installation) |
| `theme` | Browse, save, or reset a prompt theme | [Themes](themes.md) |
| `github` | Add, switch, list, and remove GitHub profiles | [GitHub accounts](github-accounts.md) |
| `skills` | Install or remove agent skills by work area | [AI skills](skills.md) |
| `guide` | Show font and default-shell instructions | [Fonts and shell](fonts-and-shell.md) |
| `doctor` / `dev-doctor` | Check tools and shell integrations | [Troubleshooting](troubleshooting.md) |
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
