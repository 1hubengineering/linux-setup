"""Shared keyboard menus, with fzf and a standard-library terminal fallback."""
import os
from functools import lru_cache
import shutil
import subprocess
import sys


def visible(value):
    return "".join(char if char.isprintable() else " " for char in str(value))


@lru_cache(maxsize=4)
def supported_fzf(path):
    """Older distro builds lack the actions used for empty checkbox selections."""
    try:
        result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
        version = tuple(int(part) for part in result.stdout.split()[0].split(".")[:2])
        return result.returncode == 0 and version >= (0, 58)
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return False


def select(title, choices, *, multi=False, default=0):
    """Return choice values; None means cancel and [] means nothing checked."""
    if not choices:
        return [] if multi else None
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RuntimeError("This menu requires an interactive terminal. Use --help for command-line options.")
    default = min(max(default, 0), len(choices) - 1)
    fzf = shutil.which("fzf")
    if fzf and supported_fzf(fzf):
        args = [fzf, "--read0", "--print0", "--delimiter=\t", "--with-nth=2..",
                "--height=~70%", "--layout=reverse", "--border", "--no-sort", "--cycle", "--sync",
                "--prompt=" + visible(title) + " > ", f"--bind=start:pos({default + 1})"]
        if multi:
            args += ["--multi", "--marker=+", "--header=Arrows: move | Space: select | Enter: confirm | Ctrl-A: all | Ctrl-D: none | Esc: back",
                     "--bind=space:toggle+down,ctrl-a:select-all,ctrl-d:deselect-all",
                     "--with-shell=/bin/sh -c",
                     '--bind=enter:transform:if [ "${FZF_SELECT_COUNT:-0}" = 0 ]; then printf "%s" "print(__NONE__)+accept"; else printf "%s" accept; fi']
        else:
            args += ["--header=Arrows: move | Type: search | Enter: select | Esc: back"]
        payload = "".join(f"{index}\t{visible(label)}\0" for index, (label, _) in enumerate(choices))
        env = dict(os.environ, FZF_DEFAULT_OPTS="", FZF_DEFAULT_OPTS_FILE="")
        result = subprocess.run(args, input=payload, text=True, stdout=subprocess.PIPE, env=env)
        if result.returncode in (1, 130):
            return None
        if result.returncode:
            raise RuntimeError("The selection menu failed. Check your terminal or use explicit command-line options.")
        rows = [row for row in result.stdout.split("\0") if row]
        if "__NONE__" in rows:
            return []
        try:
            indices = [int(row.split("\t", 1)[0]) for row in rows]
            if any(index < 0 or index >= len(choices) for index in indices):
                raise ValueError
        except ValueError:
            raise RuntimeError("Invalid selection returned by the menu") from None
        values = [choices[index][1] for index in indices]
        return values if multi else (values[0] if values else None)
    return _terminal_select(title, choices, multi, default)


def _terminal_select(title, choices, multi, default):
    """Keep standalone managers usable before fzf has been installed."""
    try:
        import curses
    except ImportError:
        raise RuntimeError("Install fzf to use the keyboard menus on this Python installation") from None

    def menu(screen):
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        screen.keypad(True)
        focus, checked = default, set()
        while True:
            height, width = screen.getmaxyx()
            if height < 6 or width < 24:
                raise RuntimeError("Enlarge your terminal to at least 24 columns and 6 rows")
            screen.erase()
            screen.addnstr(0, 0, visible(title), width - 1, curses.A_BOLD)
            hint = "Arrows: move | Space: select | Enter: confirm | Esc: back" if multi else "Arrows: move | Enter: select | Esc: back"
            screen.addnstr(1, 0, hint, width - 1)
            page = height - 4
            start = (focus // page) * page
            for row, index in enumerate(range(start, min(start + page, len(choices))), 3):
                mark = ("[x] " if index in checked else "[ ] ") if multi else ""
                line = ("> " if focus == index else "  ") + mark + visible(choices[index][0])
                screen.addnstr(row, 0, line, width - 1, curses.A_REVERSE if focus == index else curses.A_NORMAL)
            screen.refresh()
            key = screen.getch()
            if key in (27, ord("q")):
                return None
            if key == 3:
                raise KeyboardInterrupt
            if key in (curses.KEY_UP, ord("k")):
                focus = (focus - 1) % len(choices)
            elif key in (curses.KEY_DOWN, ord("j"), 9):
                focus = (focus + 1) % len(choices)
            elif key == curses.KEY_HOME:
                focus = 0
            elif key == curses.KEY_END:
                focus = len(choices) - 1
            elif key == curses.KEY_NPAGE:
                focus = min(len(choices) - 1, focus + page)
            elif key == curses.KEY_PPAGE:
                focus = max(0, focus - page)
            elif multi and key == ord(" "):
                checked.symmetric_difference_update([focus])
                focus = (focus + 1) % len(choices)
            elif multi and key == 1:
                checked = set(range(len(choices)))
            elif multi and key == 4:
                checked.clear()
            elif key in (10, 13, curses.KEY_ENTER):
                return [choices[index][1] for index in sorted(checked)] if multi else choices[focus][1]

    try:
        return curses.wrapper(menu)
    except curses.error as error:
        raise RuntimeError(f"Cannot open the terminal menu: {error}. Set TERM or install fzf.") from None


def choose(title, options):
    return select(title, [(label, index) for index, label in enumerate(options)])


def choose_many(title, options):
    return select(title, [(label, index) for index, label in enumerate(options)], multi=True) or []


def confirm(prompt, default=False):
    return select(prompt, [("Yes", True), ("No", False)], default=0 if default else 1) is True
