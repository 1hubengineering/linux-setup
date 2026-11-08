# User guides

[Project overview](../README.md) · [Terminal previews](previews.md)

## Start here

1. [Install or update linux-setup](installation.md). Update and upgrade Linux before your first clone.
2. [Install a font and set your default shell](fonts-and-shell.md). Use the Windows instructions for WSL.
3. [Find your commands](commands.md). Start with Alt+X or `devcommands`.

## Everyday tasks

| What you want to do | Guide |
| --- | --- |
| Choose, change, or reset a prompt theme | [Themes](themes.md) |
| Add a GitHub account, share author details, switch accounts, or remove a profile | [GitHub accounts](github-accounts.md) |
| Install or remove skills for your agent and work areas | [AI skills](skills.md) |
| Navigate files, use keyboard shortcuts, manage tmux sessions or ports | [Terminal commands](terminal.md) |
| Check a project or set up browser testing | [Developer workflow](developer-workflow.md) |
| Manage PostgreSQL databases and schemas | [Database manager](databases.md) |
| Rerun setup, resume after a failure, or approve updates | [Rerun and recovery](recovery.md) |
| Diagnose a tool or shell problem | [Troubleshooting](troubleshooting.md) |
| Remove setup or selected tools | [Uninstall and recovery](uninstall.md) |

## Reference and customization

- [Included tools](tools.md): what is installed, optional dependencies, Vite+, and uv.
- [Customization](customization.md): private settings, shared commands, and repository layout.
- [Preview gallery](previews.md): theme and menu images with capture instructions.
- [Development](development.md): validation, ownership rules, lockfile updates, and contributions.

## Menu controls

Use Up/Down to move and Enter to choose. Lists with multiple selections use Space
to toggle an item, Ctrl+A to select all, and Ctrl+D to clear all. Enter with
nothing checked selects nothing. Esc returns without applying that selection;
menus also offer Back or Exit where appropriate. With fzf 0.58 or newer, type to
filter the choices. When fzf is absent or older, the Python fallback uses the
same selection keys without search and supports `q` to go back. Normal setup
installs a compatible fzf.

Names, email addresses, and project paths are text fields. Administrative tools,
GitHub CLI login, and destructive-action confirmations may have their own prompts.
