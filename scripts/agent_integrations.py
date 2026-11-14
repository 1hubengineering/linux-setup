"""Add selected MCP entries without replacing existing servers or storing credentials."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

from console import status

SERVERS = {
    'oh-my-posh': {'url': 'https://ohmyposh.dev/api/mcp'},
    'better-auth': {'url': 'https://mcp.better-auth.com/mcp'},
    'shadcn': {'command': 'npx', 'args': ['--yes', 'shadcn@latest', 'mcp']},
}


def atomic_write(path, text, backups):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backups.mkdir(parents=True, exist_ok=True)
        backup = backups / (uuid.uuid4().hex + '-' + path.name)
        backup.write_bytes(path.read_bytes())
        backup.chmod(0o600)
    descriptor, temporary = tempfile.mkstemp(prefix='.linux-setup-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def configure(agent, names, scope, project, backups):
    if scope == 'global':
        if not shutil.which(agent):
            raise RuntimeError(f'{agent} is required to configure global MCP servers')
        for name in names:
            result = subprocess.run([agent, 'mcp', 'get', name] + (['--json'] if agent == 'codex' else []), capture_output=True, text=True)
            if result.returncode == 0:
                status('kept', f'{agent} MCP: {name}')
                continue
            output = result.stdout + result.stderr
            if 'No MCP server' not in output and 'not found' not in output.lower():
                raise RuntimeError(f'Cannot inspect {agent} MCP configuration; leaving it unchanged')
            server = SERVERS[name]
            command = [agent, 'mcp', 'add']
            if agent == 'claude':
                command += ['--scope', 'user']
            if 'url' in server:
                command += ([name, '--url', server['url']] if agent == 'codex' else ['--transport', 'http', name, server['url']])
            else:
                command += [name, '--', server['command']] + server['args']
            subprocess.run(command, check=True)
        return
    project = Path(project).resolve()
    if not project.is_dir():
        raise RuntimeError('The selected project no longer exists')
    if agent == 'claude':
        path = project / '.mcp.json'
        if path.is_symlink() or not path.resolve().is_relative_to(project):
            raise RuntimeError('Project MCP path is a link outside its configuration scope; kept unchanged')
        data = json.loads(path.read_text()) if path.exists() else {}
        if not isinstance(data, dict) or not isinstance(data.get('mcpServers', {}), dict):
            raise RuntimeError('Invalid project MCP configuration; leaving it unchanged')
        servers = data.setdefault('mcpServers', {})
        changed = False
        for name in names:
            if name not in servers:
                server = dict(SERVERS[name])
                if 'url' in server:
                    server['type'] = 'http'
                servers[name] = server
                changed = True
        if changed:
            atomic_write(path, json.dumps(data, indent=2) + '\n', backups)
    else:
        path = project / '.codex/config.toml'
        if path.is_symlink() or not path.resolve().is_relative_to(project):
            raise RuntimeError('Project MCP path is a link outside its configuration scope; kept unchanged')
        original = path.read_text() if path.exists() else ''
        if original.strip():
            try:
                import tomllib
            except ImportError:
                raise RuntimeError('Python 3.11+ is required to safely merge existing Codex project TOML; existing configuration was kept') from None
            data = tomllib.loads(original)
        else:
            data = {}
        existing = data.get('mcp_servers', {})
        if not isinstance(existing, dict):
            raise RuntimeError('Invalid Codex MCP configuration; leaving it unchanged')
        additions = []
        for name in names:
            if name not in existing:
                additions.append('[mcp_servers.' + json.dumps(name) + ']')
                additions.extend(key + ' = ' + json.dumps(value) for key, value in SERVERS[name].items())
                additions.append('')
        if additions:
            atomic_write(path, original.rstrip() + '\n\n' + '\n'.join(additions), backups)
    status('ok', f'{agent} project MCP: existing entries kept')


def install_uiux_plugin(scope, project, repository):
    """Use Claude's native installer with an explicit source pin and settings scope."""
    cwd = str(project) if scope == 'project' else str(Path.home())
    target_scope = 'project' if scope == 'project' else 'user'
    result = subprocess.run(['claude', 'plugin', 'marketplace', 'list', '--json'], cwd=cwd, capture_output=True, text=True, check=True)
    markets = json.loads(result.stdout)
    if not isinstance(markets, list):
        raise RuntimeError('Cannot inspect Claude plugin marketplaces; leaving them unchanged')
    existing = next((item for item in markets if item.get('name') == 'ui-ux-pro-max-skill'), None)
    if existing:
        if existing.get('repo') != repository['repo']:
            raise RuntimeError('An existing UI/UX marketplace has a different source; kept unchanged')
    else:
        source = repository['repo'] + '#' + repository['commit']
        subprocess.run(['claude', 'plugin', 'marketplace', 'add', source, '--scope', target_scope], cwd=cwd, check=True)
    subprocess.run(['claude', 'plugin', 'install', 'ui-ux-pro-max@ui-ux-pro-max-skill', '--scope', target_scope], cwd=cwd, check=True)
