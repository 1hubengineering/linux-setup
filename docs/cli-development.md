# CLI conventions and shell completion

Public commands now share version metadata from `VERSION` and support `--help`,
`--version`, and `--completion bash|zsh|fish`. Existing flags, subcommands, and
positional arguments retain their names. The first shared CLI metadata version
is `0.1.0`; this does not change the independently pinned tool versions.

```sh
./install.sh --help
./install.sh --version
dev-tools auth --help
shell-default --help
skill-manager --help
```

Version requests and cached root help do not load tool integrations, inspect
credentials, acquire an operation lock, or create setup state. Root help is
generated from the real parsers rather than maintained as separate definitions.
Malformed arguments produce usage errors on stderr and exit status 2 before
interactive prompts. Interrupted helper operations report cancellation without a
Python traceback and return 130. Cancelling an unapplied wizard plan remains a
successful no-change operation.

CI disables automatic wizard/menu selection, terminal colors, and animations,
even when the process has a terminal. Explicit `--wizard` requires a terminal
outside CI. Batch setup remains available through `--no-wizard`; authentication
and other explicitly interactive actions still require user input.

Shared status messages, headings, and progress indicators use stderr. Command
results, tables, help, versions, and generated completions use stdout. Legacy
installer/subprocess detail output retains its existing streams. JSON-capable
commands such as `dev-ports list --json` keep their existing output contracts.

## Completions

Bash and Zsh startup configuration automatically sources the checked-in completion
scripts. No CLI process starts to generate completions while opening a shell.
Reload the shell after installing the updated configuration:

```sh
reload
```

For manual setup:

```sh
# Bash
source /path/to/linux-setup/config/completions/linux-setup.bash

# Zsh, after compinit
source /path/to/linux-setup/config/completions/linux-setup.zsh

# Fish
source /path/to/linux-setup/config/completions/linux-setup.fish
```

For a single command:

```sh
dev-tools --completion bash > /tmp/dev-tools.bash
source /tmp/dev-tools.bash
```

Completion follows the selected subcommand and known argument choices, with file
completion as a fallback. The included scripts also cover common aliases such as
`theme`, `skills`, `github`, `shell`, and `default-shell`. The existing Bash and Zsh
profiles remain the supported managed profiles; a Fish completion file does not
add a managed Fish profile or change the login shell.

## Updating CLI assets

After changing a parser, regenerate help and completion files:

```sh
python3 scripts/generate-completions.py
python3 -m unittest discover -s tests -v
```

The generator runs only metadata commands and disables the cached-help fast path
for regeneration. Use Python 3.14 to reproduce the help snapshots' formatting.
Tests check public command help/version behavior in a fresh home, compare help
content across supported Python versions, and exercise Bash/Zsh completion.
Fish syntax is checked when Fish is available. The repository remains Linux/WSL
software; Windows-native and macOS application execution are not supported or tested.

Measured on the development machine, five-run median root help/version startup
was about 5 ms for the shell installer and 18–23 ms for Python helper wrappers.
These figures describe metadata requests, not installation duration or every
subcommand's cold startup. Timing varies by interpreter and filesystem.
