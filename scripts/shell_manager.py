#!/usr/bin/env python3
"""Select a session shell or change the login shell using chsh."""
import argparse
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys


def select_shell(requested, current):
    name = requested or ('bash' if Path(current).name == 'zsh' else 'zsh')
    executable = shutil.which(name)
    if not executable:
        raise RuntimeError(f'{name} is not installed.')
    return executable


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('shell', nargs='?', choices=['bash', 'zsh'])
    parser.add_argument('--default', action='store_true', help='Change the login shell rather than this session')
    parser.add_argument('--current', choices=['bash', 'zsh'], help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    account = pwd.getpwuid(os.getuid())
    current = account.pw_shell if args.default else (args.current or os.environ.get('SHELL', account.pw_shell))
    target = select_shell(args.shell, current)
    if args.default:
        # chsh validates and authenticates the actual account; never edit /etc/passwd.
        allowed = Path('/etc/shells').read_text().splitlines()
        if target not in [line.strip() for line in allowed if not line.lstrip().startswith('#')]:
            raise RuntimeError(f'{target} is not listed in /etc/shells. Ask an administrator to register it first.')
        if Path(account.pw_shell) == Path(target):
            print(f'Login shell is already {target}.')
            return 0
        subprocess.run(['chsh', '-s', target], check=True)
        print(f'Login shell changed to {target}. Sign out and in to apply it.')
    else:
        os.environ['SHELL'] = target
        os.execv(target, [target, '-l'])
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'shell-toggle: {error}', file=sys.stderr)
        sys.exit(1)
