"""Small, dependency-free terminal reports; readable in terminals and saved logs."""
from contextlib import contextmanager
import os
import shutil
import sys
import threading
import unicodedata


def plain():
    return os.environ.get('LINUX_SETUP_PLAIN', '').lower() in ('1', 'true', 'yes')


def interactive(stream=None):
    stream = sys.stdout if stream is None else stream
    return not plain() and stream.isatty() and os.environ.get('TERM', '') not in ('', 'dumb')


def unicode_output(stream):
    try:
        '─✓'.encode(stream.encoding or 'utf-8')
        return interactive(stream)
    except (UnicodeError, AttributeError):
        return False


def clean(value):
    # Do not let upstream error text inject terminal control sequences.
    return ''.join(c if c.isprintable() else ' ' for c in str(value))


def width(value):
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in value)


def wrap(value, limit):
    lines, line = [], ''
    for word in clean(value).split():
        if line and width(line + ' ' + word) <= limit:
            line += ' ' + word
            continue
        if line:
            lines.append(line)
            line = ''
        for char in word:
            if line and width(line + char) > limit:
                lines.append(line)
                line = ''
            line += char
    return lines + [line] if line or not lines else lines


def color(value, code, stream):
    if interactive(stream) and 'NO_COLOR' not in os.environ:
        return f'\033[{code}m{value}\033[0m'
    return value


def section(title, *, stream=None):
    stream = sys.stdout if stream is None else stream
    title = clean(title)
    if plain():
        print('\n' + title, file=stream, flush=True)
        return
    size = max(16, shutil.get_terminal_size((88, 24)).columns - 1)
    line = '─' if unicode_output(stream) else '-'
    print('\n' + color(title, '1;36', stream), file=stream)
    print(line * min(size, 88), file=stream, flush=True)


def status(kind, message, *, stream=None):
    stream = sys.stdout if stream is None else stream
    label, mark, code = {
        'ok': ('OK', '✓', '32'), 'kept': ('KEPT', '•', '36'),
        'warn': ('ATTENTION', '!', '33'), 'error': ('INCOMPLETE', '✗', '31'),
        'info': ('INFO', '›', '36'),
    }[kind]
    prefix = f'{mark} {label}' if unicode_output(stream) else f'[{label}]'
    print(color(prefix, code, stream) + ' ' + clean(message), file=stream, flush=True)


def table(headers, rows, *, stream=None):
    stream = sys.stdout if stream is None else stream
    rows = [[clean(value) for value in row] for row in rows]
    headers = [clean(value) for value in headers]
    columns = len(headers)
    terminal = max(20, min(110, shutil.get_terminal_size((88, 24)).columns - 1))
    if plain() or terminal < 56:
        for row in rows:
            value = ' | '.join(f'{label}: {value}' for label, value in zip(headers, row))
            for line in [value] if plain() else wrap(value, terminal):
                print(line, file=stream)
        return
    budget = terminal - 3 * columns - 1
    sizes = [max(width(row[i]) for row in [headers] + rows) for i in range(columns)]
    while sum(sizes) > budget:
        largest = max(range(columns), key=lambda i: sizes[i])
        sizes[largest] -= 1
    if unicode_output(stream):
        horizontal, vertical = '─', '│'
        joins = [('┌', '┬', '┐'), ('├', '┼', '┤'), ('└', '┴', '┘')]
    else:
        horizontal, vertical = '-', '|'
        joins = [('+', '+', '+')] * 3
    def border(index):
        left, middle, right = joins[index]
        print(left + middle.join(horizontal * (n + 2) for n in sizes) + right, file=stream)
    def render(row, heading=False):
        cells = [wrap(value, size) for value, size in zip(row, sizes)]
        for line in range(max(map(len, cells))):
            values = [cell[line] if line < len(cell) else '' for cell in cells]
            colors = {'OK': '32', 'KEPT': '36', 'INCOMPLETE': '31'}
            content = vertical + vertical.join(' ' + (color(value, colors[value], stream) if not heading and value in colors else value) + ' ' * (size - width(value) + 1) for value, size in zip(values, sizes)) + vertical
            print(color(content, '1', stream) if heading else content, file=stream)
    border(0)
    render(headers, True)
    border(1)
    for row in rows:
        render(row)
    border(2)


def progress(done, total, label='Steps checked'):
    if total <= 0:
        return
    done = min(done, total)
    if plain():
        print(f'{done}/{total} {label}', flush=True)
        return
    filled = int(20 * done / total)
    print(f'[{"#" * filled}{"." * (20 - filled)}] {done}/{total} {label}', flush=True)


@contextmanager
def busy(message):
    """Animate only silent work, never subprocess output or interactive prompts."""
    stream = sys.stderr
    reduced = os.environ.get('LINUX_SETUP_NO_ANIMATION', '') or os.environ.get('CI', '')
    if not interactive(stream) or reduced:
        yield
        return
    stopped = threading.Event()
    limit = max(12, shutil.get_terminal_size((88, 24)).columns - 5)
    label = wrap(message, limit)[0]
    def spin():
        frames = '|/-\\'
        index = 0
        while not stopped.is_set():
            stream.write('\r' + frames[index % len(frames)] + ' ' + label)
            stream.flush()
            index += 1
            stopped.wait(0.12)
    worker = threading.Thread(target=spin, daemon=True)
    worker.start()
    try:
        yield
    finally:
        stopped.set()
        worker.join()
        stream.write('\r\033[2K')
        stream.flush()
