# Customize your terminal setup

[Documentation](README.md) · [Project overview](../README.md)

## Switch the prompt theme

Run `theme-manager` to choose a bundled or upstream theme, then `reload` to apply
it. See [Themes](themes.md) for direct commands, local files, URLs, and resetting
the selection. [Font setup](fonts-and-shell.md) explains unreadable icons.

## Repository layout

```text
linux-setup/
├── install.sh                 # Bootstrap entry point
├── uninstall.sh               # Configuration, program, and cache removal
├── tools.lock.json            # Pinned release assets and plugin commits
├── bin/                       # Your portable executable scripts
├── config/
│   ├── zsh/                   # Shell settings, aliases, functions
│   ├── oh-my-posh/             # quick-term and iterm2 prompt themes
│   ├── tmux/                  # Pane, session, key, and status settings
│   ├── git/                   # Included delta settings
│   ├── bat/                   # File viewer settings
│   ├── ripgrep/               # Search settings
│   ├── yazi/                  # File manager settings
│   ├── lazygit/               # Git interface settings
│   └── codex/                 # Reference Oh My Posh MCP entry
├── scripts/                   # Installer, uninstaller, helpers, lock updater
├── docs/                      # Installation, recovery, troubleshooting, development
└── tests/                     # Installer, uninstall, helper, and isolated DB tests
```

Add shared aliases to `config/zsh/aliases.zsh`, functions to
`config/zsh/functions.zsh`, and executable scripts to `bin/`. Rerun the installer
to link new scripts. Edit the bundled default in
`config/oh-my-posh/quick-term.omp.json`. Use `reload` after changing shell
initialization or prompt settings.

Private or device-specific additions go in:

```text
~/.config/linux-setup-local/zshenv  # Environment needed by all Zsh processes
~/.config/linux-setup-local/zshrc   # Interactive additions, editor choice, local aliases
```

For example, put `export EDITOR='nvim'` in the local zshrc if Neovim is installed.
The initial migration preserves the existing Vite+ environment hook in the local
zshenv. Other old files are backed up for reference. Your Git identity, credentials,
SSH keys, shell history, project files, downloaded binaries, and private Codex
settings are not copied into the repository.

XDG config/data/cache/state directories are respected. Executables always go in
`~/.local/bin`. Rootless base-package binaries and their runtime paths are
generated separately on each device.

`LINUX_SETUP_DIR` points to the active checkout through its configuration link.
`DEV_SETUP_DIR` remains a compatibility alias for existing personal scripts.
