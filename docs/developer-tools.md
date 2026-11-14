# Developer tools and shell switching

The interactive installer starts with a [setup wizard](setup-wizard.md) to choose
programs, Codex/Claude login, integrations, scope, and Git/GitHub actions before
applying changes. Existing tools and active logins are kept. Run `dev-tools install`
or `dev-tools auth` later for individual tasks. Failed steps can be retried.
Configuration-only installs never download developer tools. `--no-wizard` retains
the earlier prompt-based flow, where declined optional offers are remembered.

For an explicit installation:

```sh
./install.sh --dev-tools
# Login is always interactive and can be run separately:
dev-tools auth
cxlogin
cldlogin
dev-tools auth codex --device
```

`./install.sh --auth` also offers authentication during initialization. Neither
login prompts nor credential contents are stored by linux-setup; the official
CLIs manage credentials. Noninteractive installs never launch a login flow.

`dev-tools install` installs the newest stable Python supported by uv without
replacing system Python, missing Codex and OpenSpec CLIs through npm under
`~/.local`, Claude Code through its official stable native installer, and Graphify
through `uv tool install graphifyy`. Node/npm must be available (Vite+ supplies
them after shell initialization). The base installer pins uv in `tools.lock.json`
(currently 0.13.8, with checksummed archives) and preserves existing uv installs.

```sh
dev-tools install --update   # Explicitly update existing managers and CLIs
uvr python --version        # Python inside the current project
uvs                         # uv sync
uva requests                # uv add requests
python-latest               # uv python install
```

These optional tools remain managed by npm, uv, and the Claude installer. Setup's
configuration restore does not uninstall them or remove their credentials. Their
own installers may keep caches and user settings.

## Skills, MCP, and project workflows

Use `skills` to install pinned, reviewed catalog sources into Codex's `.agents/skills`
or Claude's `.claude/skills`, globally or in one project. New entries include
Better Auth, shadcn/ui, Tailwind v4, modern Python typing/testing, and uv.
UI/UX Pro Max is updated to its latest reviewed source revision.

```sh
dev-tools mcp codex
dev-tools mcp claude
```

These commands add missing Better Auth documentation and shadcn MCP servers to
the selected CLI's user configuration. Existing entries are retained; inspection
errors stop changes. The shadcn server runs through `npx`, which needs Node and
network access on first use. These optional registrations are retained by setup
restore; remove them with the selected CLI's `mcp remove NAME` command.

Run project commands from the intended repository:

```sh
dev-tools workflow openspec --agent codex
# Or select Claude:
dev-tools workflow openspec --agent claude
specs                       # openspec list
spec-update                 # openspec update
dev-tools workflow graphify --agent codex
dev-tools workflow graphify --agent claude
graph --help
shadcn --help
better-auth --help
tailwind --help
```

OpenSpec and Graphify generate their own project skills/workflows. Project
initialization is explicit; rerun behavior is controlled by those tools. Better
Auth and Tailwind dependencies belong in each application's package manifest;
the aliases invoke their CLIs without adding global framework dependencies.
Use the Better Auth and UI/UX skill packs for their agent/plugin guidance.

## Bash and Zsh

Both shells have the new developer aliases, theme manager, uv completions, and
compatible existing shortcuts. Bash login and interactive startup files are
backed up and loaded through managed wrappers. Existing `.bash_login` or `.profile`
is loaded when introducing a new `.bash_profile`. Local additions belong in
`~/.config/linux-setup-local/bashenv` and `bashrc` (or the Zsh equivalents).
`./install.sh --restore` restores the original startup files.

```sh
shell                       # Replace this session with the other shell
shell bash                  # Replace this session with Bash
shell zsh                   # Replace this session with Zsh
default-shell               # Toggle the account's default login shell
default-shell bash          # Set an explicit default login shell
shell-default zsh          # Separate default-shell script
```

`default-shell` uses `chsh`, may request the account password, and takes effect on
the next login. Its target must already appear in `/etc/shells`; a user-space
wrapper needs administrator registration before it can become a login shell.
The `shell` alias uses `exec` to avoid nested shells. Invoking `shell-toggle`
directly launches a shell as a child of the calling terminal shell.

Sources: [uv Python management](https://docs.astral.sh/uv/guides/install-python/),
[Codex authentication](https://learn.chatgpt.com/docs/auth?surface=cli),
[Claude CLI reference](https://code.claude.com/docs/en/cli-reference),
[Better Auth MCP](https://better-auth.com/docs/ai-resources/mcp),
[shadcn MCP](https://ui.shadcn.com/docs/mcp),
[OpenSpec installation](https://openspec.dev/docs/installation),
[Graphify installation](https://graphiffy.com/docs/install).

See [terminal output](terminal-output.md) for status tables, download animation,
plain logs, and reduced-motion settings.
