#!/usr/bin/env python3
"""Install optional developer tools, authenticate agents, and configure integrations."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from console import busy, section, status, table


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def install(update=False, selected=None):
    """Keep existing tools and report independent failures without blocking later tools."""
    selected = set(('python', 'codex', 'openspec', 'claude', 'graphify') if selected is None else selected)
    uv = shutil.which('uv')
    if not uv and (selected.intersection({'python', 'graphify'}) or update):
        raise RuntimeError('uv is missing; run ./install.sh first.')
    failures, rows = [], []

    def attempt(name, action):
        status('info', f'{name}: checking installation')
        try:
            action()
        except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
            failures.append(name)
            rows.append((name, 'INCOMPLETE'))
            status('error', f'{name}: {str(error).rstrip(".")}.', stream=sys.stderr)
        else:
            rows.append((name, 'OK'))
            status('ok', f'{name}: ready')

    def keep(name):
        rows.append((name, 'KEPT'))
        status('kept', f'Keeping existing {name}.')

    section('Developer tools')
    if update:
        attempt('uv', lambda: run([uv, 'self', 'update']))
    if 'python' in selected:
        attempt('Python', lambda: run([uv, 'python', 'install']))
    npm = shutil.which('npm')
    if not npm:
        config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
        data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
        for directory in [data / 'vite-plus/bin', config / 'vite-plus/bin', Path.home() / '.vite-plus/bin']:
            if (directory / 'npm').is_file():
                os.environ['PATH'] = str(directory) + os.pathsep + os.environ.get('PATH', '')
                npm = str(directory / 'npm')
                break

    def npm_install(package):
        if not npm:
            raise RuntimeError('npm is required; open a new shell after installing Vite+ and retry dev-tools install')
        run([npm, 'install', '--global', '--prefix', str(Path.home() / '.local'), package + '@latest'])

    for binary, package in [('codex', '@openai/codex'), ('openspec', '@fission-ai/openspec')]:
        if binary not in selected:
            continue
        if shutil.which(binary) and not update:
            keep(binary)
        else:
            attempt(binary, lambda package=package: npm_install(package))

    def install_claude():
        with tempfile.TemporaryDirectory(prefix='linux-claude-') as directory:
            script = Path(directory) / 'install.sh'
            request = urllib.request.Request('https://claude.ai/install.sh', headers={'User-Agent': 'linux-setup/1'})
            try:
                with busy('Downloading Claude Code installer'), urllib.request.urlopen(request, timeout=60) as source:
                    script.write_bytes(source.read())
            except urllib.error.HTTPError as error:
                raise RuntimeError(f'Claude installer download returned HTTP {error.code}. Check access to https://claude.ai/install.sh, then retry dev-tools install') from None
            run(['bash', str(script), 'stable'])

    if 'claude' not in selected:
        pass
    elif not shutil.which('claude'):
        attempt('claude', install_claude)
    elif update:
        attempt('claude', lambda: run(['claude', 'update']))
    else:
        keep('claude')
    if 'graphify' not in selected:
        pass
    elif not shutil.which('graphify'):
        attempt('graphify', lambda: run([uv, 'tool', 'install', 'graphifyy']))
    elif update:
        attempt('graphify', lambda: run([uv, 'tool', 'upgrade', 'graphifyy']))
    else:
        keep('graphify')
    table(('Tool', 'Result'), rows)
    if failures:
        status('warn', 'Retry incomplete tools with dev-tools install' + (' --update' if update else '') + '.')
    else:
        status('ok', 'Developer tools ready. Use dev-tools auth, dev-tools mcp, and skills.')
    return failures


def authenticate(agent='all', device=False, method=None):
    if os.environ.get("CI") or not sys.stdin.isatty():
        raise RuntimeError('Authentication requires a terminal. Run dev-tools auth interactively.')
    missing = []
    for name, status_command, login in [
        ('codex', ['login', 'status'], ['login'] + (['--device-auth'] if device or method == 'device' else [])),
        ('claude', ['auth', 'status'], ['auth', 'login']),
    ]:
        if agent not in ('all', name):
            continue
        if not shutil.which(name):
            missing.append(name)
            continue
        result = subprocess.run([name] + status_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode == 0:
            status('kept', f'Keeping existing {name} authentication.')
            continue
        if method == 'api-key':
            variable = 'OPENAI_API_KEY' if name == 'codex' else 'ANTHROPIC_API_KEY'
            secret = os.environ.get(variable)
            if not secret:
                raise RuntimeError(f'Set {variable} privately in your environment, then retry authentication')
            if name == 'codex':
                run([name, 'login', '--with-api-key'], input=secret + '\n', text=True)
            else:
                status('ok', 'Claude will use ANTHROPIC_API_KEY from the environment; no key was saved by setup.')
        else:
            run([name] + login + (['--console'] if method == 'console' and name == 'claude' else []))
    if missing:
        raise RuntimeError('Missing CLIs: ' + ', '.join(missing) + '; run dev-tools install first.')


def mcp(agent):
    if not shutil.which(agent):
        raise RuntimeError(f'{agent} is missing; run dev-tools install first.')
    servers = [
        ('better-auth', ['--url', 'https://mcp.better-auth.com/mcp']),
        ('shadcn', ['--', 'npx', '--yes', 'shadcn@latest', 'mcp']),
    ]
    for name, arguments in servers:
        inspect = [agent, 'mcp', 'get', name] + (['--json'] if agent == 'codex' else [])
        result = subprocess.run(inspect, capture_output=True, text=True)
        if result.returncode == 0:
            print(f'Keeping existing {agent} MCP server: {name}.')
            continue
        if 'No MCP server' not in result.stdout + result.stderr and 'not found' not in (result.stdout + result.stderr).lower():
            raise RuntimeError(f'Cannot inspect {agent} MCP configuration; leaving it unchanged.')
        if agent == 'codex':
            run([agent, 'mcp', 'add', name] + arguments)
        elif arguments[0] == '--url':
            run([agent, 'mcp', 'add', '--scope', 'user', '--transport', 'http', name, arguments[1]])
        else:
            run([agent, 'mcp', 'add', '--scope', 'user', name] + arguments)


def main(argv=None):
    from cli_support import ArgumentParser
    parser = ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    installer = sub.add_parser('install', help='Keep existing tools; install missing stable releases')
    installer.add_argument('--update', action='store_true', help='Explicitly update existing managers and CLIs')
    auth = sub.add_parser('auth', help='Keep active logins; sign in when needed')
    auth.add_argument('agent', nargs='?', choices=['all', 'codex', 'claude'], default='all')
    auth.add_argument('--device', action='store_true', help='Use device authentication for Codex')
    servers = sub.add_parser('mcp', help='Add missing Better Auth and shadcn servers without replacing existing entries')
    servers.add_argument('agent', nargs='?', choices=['codex', 'claude'], default='codex')
    workflow = sub.add_parser('workflow', help='Initialize agent workflows in the current project')
    workflow.add_argument('tool', choices=['openspec', 'graphify'])
    workflow.add_argument('--agent', choices=['codex', 'claude'], default='codex')
    args = parser.parse_args(argv)
    os.environ['PATH'] = str(Path.home() / '.local/bin') + os.pathsep + os.environ.get('PATH', '')
    if args.action == 'install':
        return 1 if install(args.update) else 0
    elif args.action == 'auth':
        authenticate(args.agent, args.device)
    elif args.action == 'mcp':
        mcp(args.agent)
    else:
        if not shutil.which(args.tool):
            raise RuntimeError(f'{args.tool} is missing; run dev-tools install first.')
        if args.tool == 'openspec':
            run(['openspec', 'init', '--tools', args.agent])
        else:
            run(['graphify', args.agent, 'install', '--project'])
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\nCancelled.', file=sys.stderr)
        sys.exit(130)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'dev-tools: {error}', file=sys.stderr)
        sys.exit(1)
