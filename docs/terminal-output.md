# Readable terminal output

The installer separates preflight, numbered installation steps, the summary, and
next actions. Status icons have text labels, so color is never the only way to
spot an incomplete step. Terminal output uses cyan headings, green success,
yellow attention, red failures, and bordered tables without requiring a Nerd Font.

The summary shows the result and elapsed time for each step in the current run.
The bar counts **steps checked**, including steps that need attention; it does
not estimate downloaded bytes or claim that incomplete steps succeeded.

A redirected log looks like this (timings are illustrative):

```text
Installation summary
------------------------------------------------------------
+----------------------+------------+-------+
| Step                 | Result     | Time  |
+----------------------+------------+-------+
| base tools           | OK         | 0.1s  |
| tools and plugins    | OK         | 0.2s  |
| configuration        | OK         | 0.0s  |
| developer tools      | INCOMPLETE | 18.6s |
| agent authentication | INCOMPLETE | 0.1s  |
| GitHub and skills    | OK         | 0.0s  |
| Codex integration    | OK         | 0.0s  |
+----------------------+------------+-------+
[####################] 7/7 Steps checked
[ATTENTION] 5 successful, 2 incomplete
```

Download spinners appear only during silent network work in an interactive
terminal. They stop and clear on success, error, or interruption. Subprocess
output, authentication, and keyboard menus retain control of the terminal.
No animations or ANSI escapes are written to redirected output; tables use
ASCII borders in logs. Narrow terminals switch to wrapped, labeled rows.

```sh
./install.sh --dev-tools --auth --no-animation
./install.sh --dev-tools --auth --plain

# Apply preferences to any helper, including theme and dev-tools:
LINUX_SETUP_NO_ANIMATION=1 dev-tools install
LINUX_SETUP_PLAIN=1 dev-tools install
NO_COLOR=1 ./install.sh
```

`--plain` disables decoration and animation. `--no-animation` keeps formatting.
`NO_COLOR` disables colors while retaining borders and status labels.
`CI` also disables animation. These settings do not change installation choices.

If Claude's official installer returns HTTP 403, the output identifies Claude,
shows its download URL, and suggests `dev-tools install` as the retry command.
Other independent tools, including Graphify, are still checked. An explicit
`--dev-tools` attempt is not repeated by the interactive setup in the same run;
subsequent runs can retry incomplete tools. A partial installation still exits
with a nonzero status. Formatting does not resolve a server's access denial.
