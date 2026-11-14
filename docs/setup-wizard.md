# Choose setup actions before installing

Run `./install.sh` in a terminal to open the keyboard wizard. `./install.sh --wizard`
requests it explicitly. Planning detects installed tools and reads existing
settings without downloading tools, writing configuration, or creating installer
state. Nothing is applied until you choose **Apply selected changes** on the final
review screen. The review defaults to **Edit selections**.

## Flow

1. **Programs:** use recommended missing terminal tools, choose individual programs
   and Zsh plugins, or skip installation. Installed tools are labeled and kept;
   the wizard does not upgrade them. Shell configuration is a separate opt-in
   choice, with startup-file backups. You can skip it independently.
2. **Agents:** installed Codex/Claude agents are preselected. Clear or change the
   selection as needed. Selecting a missing agent explicitly adds its CLI to the
   plan. Authentication is optional: keep existing credentials, use browser
   sign-in, select Codex device login, or use an existing API-key environment
   variable. Claude also offers Anthropic Console login for API billing.
3. **Scope:** choose global or an existing project directory for agent skills and
   MCP. Shell profiles and program binaries apply to the current user account;
   authentication stays in official credential stores or environment variables.
4. **Integrations:** choose skills/plugin guidance, MCP servers, native Claude plugins, and project
   workflows separately for each selected agent. No integrations are mandatory.
   UI/UX Pro Max is available as a native Claude plugin from its pinned marketplace,
   or as a portable skill for either agent. The native plugin uses scoped Claude
   settings plus its normal user plugin cache. OpenSpec and Graphify workflows always target an explicit project directory,
   even when skills/MCP are global. Their native generators may show additional
   tool-specific prompts while applying the reviewed actions.
5. **Git/GitHub:** choose global Git author settings, GitHub browser authentication,
   additional saved author profiles, or an existing profile for a Git repository.
   These are independent actions. Existing saved profiles are kept. Selecting an
   existing profile updates that repository's Git author and switches the active
   GitHub CLI account; it does not change the global author.
6. **Review:** inspect programs, prerequisites, authentication methods, identities,
   profile names, configuration scopes, and destinations. Apply, edit, or cancel.

Dependencies are included explicitly in the review: Python/Graphify may need uv;
Codex/OpenSpec or the shadcn MCP server may need Vite+'s Node/npm environment;
GitHub login/account switching may need `gh`. Only missing selected programs and
these displayed dependencies are installed. Installation order follows those
dependencies. Existing tools and credentials are retained on every rerun.

## Keyboard controls

| Key | Action |
| --- | --- |
| Up / Down | Move between choices |
| Space | Toggle a checkbox in a multi-select menu |
| Enter | Accept the highlighted choice or checked items |
| Esc | Return to the previous wizard page; at the first page, cancel |
| Ctrl-A | Select all items in a multi-select menu |
| Ctrl-D | Clear all items in a multi-select menu |
| Ctrl-S | Skip the current optional question |
| Ctrl-X / Ctrl-C | Cancel the wizard without applying the plan |
| Home / End, Page Up / Down | Navigate long lists |

fzf also supports typing to filter options. Before fzf is installed, the built-in
curses menu provides arrow/checkbox navigation without a download. Pressing Enter
with no boxes checked selects nothing. Skip and Back are distinct; going back
preserves previous choices. Text fields accept `:back` to return to the previous
page, and Ctrl-C cancels. No password or API-key text fields are presented.

## Where files go

| Item | Global | Project |
| --- | --- | --- |
| Codex skills | `~/.agents/skills/` | `<project>/.agents/skills/` |
| Claude skills | `~/.claude/skills/` or `$CLAUDE_CONFIG_DIR/skills/` | `<project>/.claude/skills/` |
| Codex MCP | `$CODEX_HOME/config.toml` or `~/.codex/config.toml` | `<project>/.codex/config.toml` |
| Claude MCP | CLI-managed `~/.claude.json` or `$CLAUDE_CONFIG_DIR/.claude.json` | `<project>/.mcp.json` |
| Workflows | Not generated globally by this wizard | Selected project; generator creates agent skills/commands |
| Git author | Git's global configuration | Repository configuration when applying a saved profile |
| Saved GitHub author profiles | `$XDG_CONFIG_HOME/linux-setup-local/git-profiles.json` | Referenced when selecting an account for a repository |

Existing MCP servers and skills are kept. Project MCP edits preserve unrelated
settings and back up existing files under the setup backup directory with private
permissions. Existing Codex TOML requires Python 3.11+ for safe parsing/merging;
older interpreters leave it unchanged and report the incomplete action. New
Codex project files can be created on all supported Python versions. Project
Codex configuration remains subject to Codex's normal project trust settings.

API keys must already be in `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`. Codex receives
its key through stdin; Claude reads its environment. The plan never stores keys,
passwords, or credential-file contents. Authentication uses each CLI's existing
private storage, regardless of integration scope.

## Batch and targeted commands

```sh
./install.sh --wizard
./install.sh --wizard --config-only  # No program downloads
./install.sh --no-wizard            # Explicit legacy installation flow
./install.sh --no-wizard --dev-tools --auth
./install.sh --dry-run              # Read-only batch plan; no wizard
```

Noninteractive invocations retain the batch behavior for automation; they never
open a keyboard wizard. `--wizard` requires both input and output to be terminals.
`--dev-tools` seeds the recommended developer-program choices and `--auth` seeds
browser login choices; the review still controls what is applied. `--skip-mcp`
removes MCP choices. `--plain` and `--no-animation` control presentation.

Python 3.9+, Bash, and the prerequisite tools must be available to run the wizard.
The explicit `--install-prerequisites` bootstrap is a separate, earlier system
package action and retains its own confirmation before running APT.

Sources: [Codex authentication](https://learn.chatgpt.com/docs/auth),
[Codex configuration](https://learn.chatgpt.com/docs/config-file/config-basic),
[Claude CLI authentication](https://code.claude.com/docs/en/cli-reference),
[Claude configuration](https://code.claude.com/docs/en/settings),
[Claude plugin commands](https://code.claude.com/docs/en/plugins/cli-reference),
[Graphify project installation](https://graphiffy.com/docs/install).
