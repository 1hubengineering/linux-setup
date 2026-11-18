#!/usr/bin/env python3
"""Describe live Bash and Zsh commands without evaluating their definitions."""
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
ALIAS = re.compile(r"(?:^|\s|[;&])alias\s+(?:--\s+)?([^\s=]+)=")
FUNCTION = re.compile(r"^\s*(?:function\s+([^\s(){]+)(?:\s*\(\s*\))?|([^\s(){]+)\s*\(\s*\))\s*\{")


def descriptions(paths):
    """Read adjacent comments. The calling shell supplies the live definitions."""
    result = {}
    for path in paths:
        if not path.is_file():
            continue
        comments = []
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                comments.append(stripped.lstrip("# "))
                continue
            alias = ALIAS.search(line)
            function = FUNCTION.match(line)
            if alias or function:
                name = alias[1] if alias else (function[1] or function[2])
                kind = "alias" if alias else "function"
                result[(kind, name)] = " ".join(comments) or f"Custom {kind}."
            # A conditional guard can sit between a description and its alias.
            if not stripped.startswith("if "):
                comments = []
    return result


def source_paths(shell="zsh"):
    config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    managed = ROOT / "config" / shell
    local = config / "linux-setup-local"
    extension = "sh" if shell == "bash" else "zsh"
    paths = [managed / ("aliases." + extension), ROOT / "config/shell/developer-aliases.sh"]
    if shell == "zsh":
        paths.append(managed / "functions.zsh")
    return paths + [managed / ("command-picker." + extension), managed / (shell + "rc"),
                    local / (shell + "env"), local / (shell + "rc")]


def catalog(snapshot, metadata, shell="zsh"):
    fields = snapshot.split("\0")
    if fields[-1] == "":
        fields.pop()
    if len(fields) % 3:
        raise ValueError("Incomplete shell command snapshot")
    entries = {}
    for kind, name, body in zip(fields[::3], fields[1::3], fields[2::3]):
        if (kind, name) not in metadata or name.startswith("_"):
            continue
        # Aliases take precedence when both kinds have the same name.
        if name in entries and entries[name]["kind"] == "alias":
            continue
        entries[name] = {
            "name": name,
            "kind": kind,
            "description": metadata[(kind, name)],
            # Bash's declare -f already includes the name and outer braces.
            "command": body if kind == "alias" or shell == "bash" else f"{name} () {{\n{body}\n}}",
            "insert": body if kind == "alias" else shlex.quote(name) + " ",
        }
    return sorted(entries.values(), key=lambda entry: entry["name"].casefold())


def single_line(value):
    # Do not let control characters in a command alter fzf's rows or terminal.
    return " ".join("".join(c if c.isprintable() else " " for c in value).split())


def row(entry):
    return "\t".join(single_line(entry[key]) for key in ("name", "kind", "description", "command"))


def list_commands(entries, query):
    matches = [entry for entry in entries if query.casefold() in row(entry).casefold()]
    if not sys.stdout.isatty():
        for entry in matches:
            print(row(entry))
        return
    from console import table
    if matches:
        table(("Shortcut", "Type", "Description"),
              [(entry["name"], entry["kind"], entry["description"]) for entry in matches])
        print(f"{len(matches)} commands. Press Alt+X to preview a definition or insert a command.")
    else:
        print("No matching commands.")


def pick(entries, query=""):
    if not entries:
        return None
    # Full definitions are plain preview files. Only opaque numeric IDs enter
    # the preview shell command; no alias/function is ever used as shell code.
    with tempfile.TemporaryDirectory(prefix="linux-setup-commands-") as temporary:
        directory = Path(temporary)
        for index, entry in enumerate(entries):
            hint = "Enter inserts the expansion" if entry["kind"] == "alias" else f"Enter inserts {entry['name']} for editing"
            definition = "".join(c if c.isprintable() or c in "\n\t" else " " for c in entry["command"])
            (directory / str(index)).write_text(
                f"# {single_line(entry['name'])} ({entry['kind']}) | {single_line(hint)}\n"
                f"# {single_line(entry['description'])}\n\n# Full command:\n{definition}\n"
            )
        from console import plain
        monochrome = "NO_COLOR" in os.environ or plain() or os.environ.get("TERM") == "dumb"
        bat = shutil.which("bat") or shutil.which("batcat")
        viewer = [bat, "--paging=never", "--language=bash", "--style=plain",
                  "--color=never" if monochrome else "--color=always"] if bat else ["cat"]
        preview = shlex.join(viewer + ["--"]) + " " + shlex.quote(str(directory)) + "/{1}"
        result = subprocess.run(
            [
                "fzf", "--height=80%", "--layout=reverse", "--border", "--no-multi",
                "--delimiter=\t", "--with-nth=2..", "--prompt=Commands> ",
                "--border-label= My commands ", "--highlight-line", "--no-hscroll",
                "--header=Enter insert · Esc cancel · Ctrl-/ preview · Shift-↑/↓ scroll preview",
                "--bind=ctrl-/:toggle-preview,shift-up:preview-up,shift-down:preview-down",
                "--preview-window=right,50%,wrap,<50(down,50%,wrap)", "--preview", preview,
                *(["--no-color"] if monochrome else []),
                "--query", query,
            ],
            input="".join(f"{index}\t{row(entry)}\n" for index, entry in enumerate(entries)),
            text=True,
            stdout=subprocess.PIPE,
            # User fzf bindings (execute, become, accept on focus, etc.) must
            # not change this picker's insert-only behavior.
            env={**os.environ, "FZF_DEFAULT_OPTS": "", "FZF_DEFAULT_OPTS_FILE": "", "SHELL": "/bin/sh"},
        )
        if result.returncode in (1, 130):
            return None
        if result.returncode:
            raise RuntimeError(f"fzf exited with status {result.returncode}")
        identifier = result.stdout.partition("\t")[0]
        if not identifier.isdecimal() or int(identifier) >= len(entries):
            raise ValueError("Invalid command selection")
        return entries[int(identifier)]["insert"]


def main():
    from cli_support import ArgumentParser
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--shell", choices=("bash", "zsh"), default="zsh")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true")
    mode.add_argument("--pick", action="store_true")
    parser.add_argument("query", nargs="?", default="")
    args = parser.parse_args()
    try:
        entries = catalog(sys.stdin.read(), descriptions(source_paths(args.shell)), args.shell)
        if args.list:
            list_commands(entries, args.query)
            return 0
        selected = pick(entries, args.query)
        if selected is None:
            return 1
        sys.stdout.write(selected)
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Command picker: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
