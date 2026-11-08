#!/usr/bin/env python3
"""Render documentation images from real prompts and an isolated fzf terminal.

Run with: uv run --with cairosvg==2.9.1 --with pyte==0.8.2 scripts/render-previews.py
Requires zsh, fzf, oh-my-posh, MesloLGM Nerd Font Mono, and Noto Emoji.
"""
import fcntl
import argparse
import html
import json
import os
from pathlib import Path
import pty
import select
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time

import cairosvg
import pyte

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'docs/assets'
COLUMNS = 112
FONT = 'MesloLGM Nerd Font Mono'
PALETTE = {
    'black': '#111827', 'red': '#f87171', 'green': '#a3e635', 'brown': '#fbbf24',
    'blue': '#60a5fa', 'magenta': '#c084fc', 'cyan': '#22d3ee', 'white': '#e2e8f0',
    'brightblack': '#64748b', 'brightred': '#fca5a5', 'brightgreen': '#bef264',
    'brightbrown': '#fde68a', 'brightblue': '#93c5fd', 'brightmagenta': '#d8b4fe',
    'brightcyan': '#67e8f9', 'brightwhite': '#f8fafc',
}


def color(value, fallback):
    if value == 'default':
        return fallback
    return PALETTE.get(value, '#' + value)


def render(screen, name, title):
    """Draw terminal cells, preserving ANSI colors and the exact visible text."""
    cell, line, left, top = 9.64, 23, 24, 70
    width, height = COLUMNS * cell + left * 2, screen.lines * line + top + 18
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           f'<rect width="{width}" height="{height}" rx="12" fill="#0f172a"/>',
           f'<path d="M12 0 H{width-12} Q{width} 0 {width} 12 V44 H0 V12 Q0 0 12 0" fill="#1e293b"/>',
           '<circle cx="24" cy="22" r="5" fill="#f87171"/><circle cx="42" cy="22" r="5" fill="#fbbf24"/><circle cx="60" cy="22" r="5" fill="#a3e635"/>',
           f'<text x="{width/2}" y="27" text-anchor="middle" fill="#cbd5e1" font-family="sans-serif" font-size="13">{html.escape(title)}</text>',
           f'<g font-family="{FONT}, monospace" font-size="16">']
    for y in range(screen.lines):
        for x in range(screen.columns):
            char = screen.buffer[y].get(x, screen.default_char)
            fg, bg = color(char.fg, '#e2e8f0'), color(char.bg, '#0f172a')
            if char.reverse:
                fg, bg = bg, fg
            px, py = left + x * cell, top + y * line
            if bg != '#0f172a':
                svg.append(f'<rect x="{px}" y="{py-17}" width="{cell+0.3}" height="{line}" fill="{bg}"/>')
            if char.data.strip():
                style = ' font-weight="bold"' if char.bold else ''
                if any(ord(c) >= 0x1F000 for c in char.data):
                    style += ' font-family="Noto Emoji"'
                svg.append(f'<text x="{px}" y="{py}" fill="{fg}"{style}>{html.escape(char.data)}</text>')
    svg.append('</g></svg>')
    output = ASSETS / (name + '.svg')
    output.write_text('\n'.join(svg) + '\n')
    cairosvg.svg2png(url=str(output), write_to=str(ASSETS / (name + '.png')), scale=2)


def shell_prelude():
    data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'linux-setup'
    modules = list((data / 'runtime/usr/lib').glob('*/zsh/*'))
    modules += list((data / 'base/zsh/runtime/usr/lib').glob('*/zsh/*'))
    return 'module_path=(' + ' '.join(shlex.quote(str(p)) for p in modules) + ' $module_path)\n' + '\n'.join(
        'source ' + shlex.quote(str(ROOT / 'config/zsh' / name))
        for name in ['aliases.zsh', 'functions.zsh', 'command-picker.zsh']
    ) + '\n'


def sample_environment(directory):
    return {**os.environ, 'LINUX_SETUP_DIR': str(ROOT), 'ZDOTDIR': directory,
            'XDG_CONFIG_HOME': directory, 'TERM': 'xterm-256color', 'COLORTERM': 'truecolor',
            'FZF_DEFAULT_OPTS': '', 'FZF_DEFAULT_OPTS_FILE': ''}


def theme_previews():
    with tempfile.TemporaryDirectory(prefix='linux-setup-preview-') as directory:
        listing = subprocess.check_output(
            ['zsh', '-dfc', shell_prelude() + "devhelp 'pnpm run'"],
            cwd=ROOT, env=sample_environment(directory), text=True,
        )
    for name in ['quick-term', 'iterm2']:
        prompt = subprocess.check_output([
            'oh-my-posh', 'print', 'primary', '--config', str(ROOT / f'config/oh-my-posh/{name}.omp.json'),
            '--data', str(ASSETS / 'prompt.data.json'), '--data-only', '--shell', 'bash',
            '--escape=false', '--terminal-width', str(COLUMNS),
        ], text=True)
        screen = pyte.Screen(COLUMNS, 18)
        stream = pyte.Stream(screen)
        stream.feed(prompt.replace('\n', '\r\n'))
        stream.feed("devhelp 'pnpm run'\r\n")
        stream.feed(listing.replace('\n', '\r\n'))
        stream.feed(prompt.replace('\n', '\r\n'))
        last = max(y for y, row in enumerate(screen.display) if row.strip())
        cropped = pyte.Screen(COLUMNS, last + 2)
        for y in range(cropped.lines):
            cropped.buffer[y] = screen.buffer[y].copy()
        render(cropped, name, f'linux-setup  /  {name}  /  Zsh')


def custom_theme_gallery():
    """Compare the distinct custom prompt layouts, including compact command history."""
    names = ['setup-wholespace', 'setup-unicorn', 'setup-tiwahu', 'setup-spaceship', 'setup-night-owl', 'setup-kali']
    screen = pyte.Screen(COLUMNS, len(names) * 6)
    stream = pyte.Stream(screen)
    for name in names:
        stream.feed(name + '\r\n')
        common = ['--config', str(ROOT / f'config/oh-my-posh/{name}.omp.json'),
                  '--data', str(ASSETS / 'prompt.data.json'), '--data-only', '--shell', 'bash',
                  '--escape=false', '--terminal-width', str(COLUMNS)]
        transient = subprocess.check_output(['oh-my-posh', 'print', 'transient', *common], text=True)
        primary = subprocess.check_output(['oh-my-posh', 'print', 'primary', *common], text=True)
        stream.feed(transient.replace('\n', '\r\n') + 'git status --short\r\n')
        stream.feed(primary.replace('\n', '\r\n') + 'npm run dev\r\n\r\n')
    last = max(y for y, row in enumerate(screen.display) if row.strip())
    cropped = pyte.Screen(COLUMNS, last + 2)
    for y in range(cropped.lines):
        cropped.buffer[y] = screen.buffer[y].copy()
    render(cropped, 'custom-themes', 'linux-setup  /  custom themes  /  parent and current folder')


def picker_preview():
    """Capture fzf itself; cancel before any command can be selected or run."""
    with tempfile.TemporaryDirectory(prefix='linux-setup-picker-preview-') as directory:
        child, master = pty.fork()
        if child == 0:
            os.execve(shutil.which('zsh'), ['zsh', '-dfi'], sample_environment(directory))
        try:
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', 34, COLUMNS, 0, 0))
            prelude = shell_prelude() + "PROMPT='preview> '\n_dev_commands_select docker\n"
            os.write(master, prelude.encode())
            captured = b''
            deadline, last_output = time.monotonic() + 12, time.monotonic()
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    captured += os.read(master, 65536)
                    last_output = time.monotonic()
                if b'Full command:' in captured and time.monotonic() - last_output > 0.5:
                    break
            else:
                raise RuntimeError('fzf preview did not finish rendering')
            screen = pyte.Screen(COLUMNS, 34)
            pyte.Stream(screen).feed(captured.decode(errors='replace'))
            rows = screen.display
            # fzf --height keeps the old prompt above it. Crop to its real border.
            first = next(i for i, row in enumerate(rows) if '╭─' in row)
            last = max(i for i, row in enumerate(rows) if '╰─' in row)
            cropped = pyte.Screen(COLUMNS, last - first + 1)
            for y in range(cropped.lines):
                cropped.buffer[y] = screen.buffer[first + y].copy()
            render(cropped, 'command-picker', 'linux-setup  /  Alt+X command picker  /  search: docker')
            os.write(master, b'\x1b')
        finally:
            os.kill(child, signal.SIGTERM)
            os.close(master)
            os.waitpid(child, 0)


def skill_manager_preview():
    """Capture the real skill selection menu without installing anything."""
    catalog = json.loads((ROOT / 'skills.catalog.json').read_text())
    areas = sorted({area for item in catalog['skills'] if 'codex' in item['agents'] for area in item['areas']})
    with tempfile.TemporaryDirectory(prefix='linux-setup-skills-preview-') as directory:
        child, master = pty.fork()
        if child == 0:
            environment = sample_environment(directory)
            environment['HOME'] = directory
            os.execve(sys.executable, [sys.executable, str(ROOT / 'scripts/skill_manager.py')], environment)
        try:
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', 40, COLUMNS, 0, 0))
            captured = b''
            offset = 0
            for prompt, answer in [
                (b'AI skill manager', b'\r'),  # Install skills
                (b'Which AI app do you use?', b'\r'),  # Codex
                (b'Where should these skills be available?', b'\r'),  # Global
                (b'Choose your work areas', b'\x1b[B' * areas.index('UI and UX') + b' \r'),
                (b'Select skills to install', None),
            ]:
                deadline = time.monotonic() + 10
                while prompt not in captured[offset:]:
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Skill manager preview did not reach the expected menu')
                    if select.select([master], [], [], 0.1)[0]:
                        captured += os.read(master, 65536)
                offset = len(captured)
                if answer is not None:
                    time.sleep(0.2)
                    os.write(master, answer)
            # The prompt is drawn before fzf finishes drawing its result rows.
            deadline = time.monotonic() + 0.5
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.05)[0]:
                    captured += os.read(master, 65536)
            screen = pyte.Screen(COLUMNS, 40)
            pyte.Stream(screen).feed(captured.decode(errors='replace'))
            first = max(0, next(i for i, row in enumerate(screen.display) if 'Select skills to install' in row) - 1)
            last = max(i for i, row in enumerate(screen.display) if row.strip())
            cropped = pyte.Screen(COLUMNS, last - first + 2)
            for y in range(last - first + 1):
                cropped.buffer[y] = screen.buffer[first + y].copy()
            render(cropped, 'skill-manager', 'linux-setup  /  skill manager  /  UI and UX')
            os.write(master, b'\x03')
        finally:
            os.kill(child, signal.SIGTERM)
            os.close(master)
            os.waitpid(child, 0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skills-only', action='store_true', help='Render only the skill manager preview')
    parser.add_argument('--themes-only', action='store_true', help='Render only theme previews and the custom theme gallery')
    args = parser.parse_args()
    ASSETS.mkdir(exist_ok=True)
    if not args.skills_only:
        theme_previews()
        custom_theme_gallery()
        if not args.themes_only:
            picker_preview()
    if not args.themes_only:
        skill_manager_preview()
    print('Rendered terminal previews in docs/assets/')
