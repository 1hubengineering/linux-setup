"""Read-only setup planning followed by explicit, scoped execution."""
from copy import deepcopy
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile

from console import section, status, table
from terminal_ui import select, SKIP

DEV = ('python', 'codex', 'claude', 'openspec', 'graphify')


class Back(Exception):
    pass


@dataclass
class Plan:
    programs: list = field(default_factory=list)
    programs_mode: str = 'recommended'
    agents: list = field(default_factory=list)
    agents_visited: bool = False
    auth: dict = field(default_factory=dict)
    scope: str = 'global'
    project: str = ''
    workflow_project: str = ''
    shell_config: bool = True
    integrations: dict = field(default_factory=dict)
    skills: dict = field(default_factory=dict)
    mcp: dict = field(default_factory=dict)
    workflows: dict = field(default_factory=dict)
    plugins: dict = field(default_factory=dict)
    git_identity: dict = field(default_factory=dict)
    github_login: bool = False
    profiles: list = field(default_factory=list)
    use_profile: str = ''
    profile_project: str = ''
    dependencies: list = field(default_factory=list)


def pick(title, choices, *, multi=False, selected=(), default=0, skip=True):
    value = select(title, choices, multi=multi, selected=selected, default=default, allow_skip=skip)
    if value is None:
        raise Back
    return ([] if multi else None) if value is SKIP else value


def text(prompt, default=''):
    value = input(prompt + (f' [{default}]' if default else '') + ' (type :back to go back): ').strip()
    if value == ':back':
        raise Back
    value = value or default
    if not value or any(not c.isprintable() for c in value):
        raise ValueError('Enter a nonempty value without control characters')
    return value


def project_path(prompt, default='.'):
    path = Path(text(prompt, default)).expanduser().resolve()
    if not path.is_dir():
        raise ValueError('Choose an existing project directory')
    return str(path)


def detected(name, setup):
    if name == 'python':
        # The system interpreter bootstraps setup; it is not a uv-managed runtime.
        root = Path(os.environ.get('UV_PYTHON_INSTALL_DIR', setup.DATA.parent / 'uv/python'))
        if root.is_dir():
            for candidate in sorted(root.glob('cpython-*/bin/python3*')):
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    return str(candidate)
        return None
    if name in setup.BASE or name in DEV or name == 'gh':
        return shutil.which('python3' if name == 'python' else name)
    if name in ('zsh-autosuggestions', 'zsh-syntax-highlighting'):
        path = setup.DATA / 'plugins' / name / 'current'
        return str(path) if path.is_dir() else None
    return setup.find_tool(setup.TOOLS.get(name, name))


def programs_page(plan, setup, lock, args):
    choices = list(setup.BASE) + list(lock['tools']) + list(lock['plugins']) + list(DEV) + ['gh']
    choices = list(dict.fromkeys(choices))
    if not args.config_only:
        table(('Available program / plugin', 'Detected status'), [(name, 'Installed — keep' if detected(name, setup) else 'Not installed') for name in choices])
        mode = pick('Programs: keep installed tools; choose what to add', [
            ('Recommended: missing terminal tools only', 'recommended'),
            ('Custom: select programs and plugins', 'custom'),
            ('Skip all program installation', 'skip')], default=['recommended', 'custom', 'skip'].index(plan.programs_mode), skip=True)
        plan.programs_mode = mode or 'skip'
        if mode == 'recommended':
            recommended = list(setup.BASE) + list(lock['tools']) + list(lock['plugins'])
            if args.dev_tools:
                recommended += list(DEV)
            plan.programs = [name for name in recommended if not detected(name, setup)]
        elif mode == 'custom':
            labels = []
            for name in choices:
                existing = detected(name, setup)
                note = f'installed; keep {existing}' if existing else 'not installed'
                if name == 'python':
                    note = 'optional latest stable Python via uv; system Python is kept'
                labels.append((f'{name} — {note}', name))
            plan.programs = pick('Programs: Space toggles; installed selections are kept', labels, multi=True, selected=plan.programs)
        else:
            plan.programs = []
    choice = pick('Shell configuration (always applies to this user account)', [
        ('Install Bash/Zsh profiles, theme, aliases, and helper scripts; back up existing files', True),
        ('Skip shell configuration; install selected programs/integrations only', False)], default=0 if plan.shell_config else 1, skip=True)
    plan.shell_config = choice is True


def agents_page(plan, setup, lock, args):
    initial = plan.agents if plan.agents_visited else [agent for agent in ('codex', 'claude') if detected(agent, setup) or agent in plan.programs]
    choices = [(f'{agent} — ' + ('installed; keep CLI' if detected(agent, setup) else 'missing; selecting installs its CLI'), agent) for agent in ('codex', 'claude')]
    plan.agents = pick('AI agents (optional; choose one, both, or skip)', choices, multi=True, selected=initial)
    plan.agents_visited = True
    for agent in plan.agents:
        if not detected(agent, setup) and agent not in plan.programs:
            if args.config_only:
                raise ValueError(f'{agent} is not installed; config-only cannot install it. Select an installed agent or skip.')
            # Missing selected agents are derived at review, so deselecting removes them.
    plan.auth = {key: value for key, value in plan.auth.items() if key in plan.agents}
    for agent in plan.agents:
        options = [('Keep existing authentication / skip sign-in', 'skip'), ('Browser sign-in (subscription)', 'browser')]
        if agent == 'codex':
            options += [('Device-code sign-in (headless)', 'device'), ('API billing using existing OPENAI_API_KEY', 'api-key')]
        else:
            options += [('Anthropic Console sign-in (API billing)', 'console'), ('Use existing ANTHROPIC_API_KEY environment variable', 'api-key')]
        values = [value for _, value in options]
        initial = plan.auth.get(agent, 'browser' if args.auth else 'skip')
        plan.auth[agent] = pick(f'{agent}: authentication; active logins are always kept', options, default=values.index(initial)) or 'skip'


def scope_page(plan, setup, lock, args):
    if not plan.agents:
        return
    value = pick('Skills and MCP configuration scope', [
        ('Global: available to this account in all projects', 'global'),
        ('Project: only in an existing project directory', 'project')], default=0 if plan.scope == 'global' else 1, skip=False)
    plan.scope = value
    if value == 'project':
        plan.project = project_path('Project directory', plan.project or '.')
    print('Authentication stays in the official CLI credential store or your environment, regardless of scope.')
    print('Project workflows always require a project folder; no passwords or API keys are collected.')


def integrations_page(plan, setup, lock, args):
    catalog = json.loads((setup.ROOT / 'skills.catalog.json').read_text())
    for mapping in (plan.integrations, plan.skills, plan.mcp, plan.workflows, plan.plugins):
        for key in list(mapping):
            if key not in plan.agents:
                del mapping[key]
    for agent in plan.agents:
        categories = [('Skills and plugin guidance (pinned catalog)', 'skills'), ('MCP documentation/component servers', 'mcp'), ('Project workflows (OpenSpec / Graphify)', 'workflows')]
        if agent == 'claude':
            categories.append(('Native Claude plugins (pinned marketplace)', 'plugins'))
        if args.skip_mcp:
            categories = [item for item in categories if item[1] != 'mcp']
        selected = pick(f'{agent}: optional integrations', categories, multi=True, selected=plan.integrations.get(agent, []))
        plan.integrations[agent] = selected
        plan.skills.setdefault(agent, [])
        plan.mcp.setdefault(agent, [])
        plan.workflows.setdefault(agent, [])
        plan.plugins[agent] = pick('Claude native plugins (optional)', [('UI/UX Pro Max — native plugin; existing installation kept', 'ui-ux-pro-max')], multi=True, selected=plan.plugins.get(agent, [])) if 'plugins' in selected else []
        if 'skills' in selected:
            available = [item for item in catalog['skills'] if agent in item['agents']]
            plan.skills[agent] = pick(f'{agent}: skills (existing directories are kept)', [(item['id'] + ' — ' + item['description'], item['id']) for item in available], multi=True, selected=plan.skills[agent])
        else:
            plan.skills[agent] = []
        if 'mcp' in selected:
            plan.mcp[agent] = pick(f'{agent}: MCP servers', [('Oh My Posh', 'oh-my-posh'), ('Better Auth docs', 'better-auth'), ('shadcn/ui components', 'shadcn')], multi=True, selected=plan.mcp[agent])
        else:
            plan.mcp[agent] = []
        if 'workflows' in selected:
            plan.workflows[agent] = pick(f'{agent}: project generators (may create agent skills and commands)', [('OpenSpec', 'openspec'), ('Graphify', 'graphify')], multi=True, selected=plan.workflows[agent])
        else:
            plan.workflows[agent] = []
    if any(plan.workflows.values()):
        plan.workflow_project = plan.project if plan.scope == 'project' else project_path('Directory for project workflows', plan.workflow_project or '.')


def git_page(plan, setup, lock, args):
    import git_profiles
    saved = git_profiles.load_profiles()
    choices = [('Global Git author name/email', 'identity'), ('GitHub account browser sign-in', 'login'), ('Add saved GitHub author profiles (no passwords)', 'profiles')]
    if saved:
        choices.append(('Use an existing saved GitHub profile for a project', 'use'))
    initial = (['identity'] if plan.git_identity else []) + (['login'] if plan.github_login else []) + (['profiles'] if plan.profiles else []) + (['use'] if plan.use_profile else [])
    actions = pick('Git / GitHub: independent optional steps', choices, multi=True, selected=initial)
    plan.github_login = 'login' in actions
    if 'identity' in actions:
        current = {}
        if shutil.which('git'):
            for key in ('name', 'email'):
                result = subprocess.run(['git', 'config', '--global', '--get', 'user.' + key], capture_output=True, text=True)
                if result.returncode not in (0, 1):
                    raise RuntimeError('Cannot read global Git identity; no changes were made')
                current[key] = result.stdout.strip()
        plan.git_identity = {key: text('Global Git ' + key, plan.git_identity.get(key, current.get(key, ''))) for key in ('name', 'email')}
    else:
        plan.git_identity = {}
    if 'profiles' in actions:
        profiles = []
        while True:
            previous = plan.profiles[len(profiles)] if len(profiles) < len(plan.profiles) else {}
            username = text('GitHub username (existing saved profiles are kept)', previous.get('username', ''))
            if username in saved or any(item['username'] == username for item in profiles):
                status('kept', f'Saved profile {username} already exists')
            else:
                profiles.append({'username': username, 'name': text('Commit author name', previous.get('name', plan.git_identity.get('name', ''))), 'email': text('Commit author email', previous.get('email', plan.git_identity.get('email', '')))})
            more = pick('Add another saved profile?', [('Continue', False), ('Add another account', True)], default=1 if len(profiles) < len(plan.profiles) else 0)
            if not more:
                break
        plan.profiles = profiles
    else:
        plan.profiles = []
    plan.use_profile = ''
    if 'use' in actions:
        plan.use_profile = pick('Existing profile to use for a project', [(name, name) for name in sorted(saved)]) or ''
        if plan.use_profile:
            plan.profile_project = project_path('Git repository for this profile', plan.project or plan.profile_project or '.')
            result = subprocess.run(['git', '-C', plan.profile_project, 'rev-parse', '--git-dir'], capture_output=True, text=True)
            if result.returncode:
                raise ValueError('Profile selection requires an existing Git repository')


def resolve_dependencies(plan, setup, args):
    """Derive only prerequisites for requested actions; show them at review."""
    needed = [agent for agent in plan.agents if not detected(agent, setup)]
    requested = set(plan.programs + needed)
    if requested.intersection({'python', 'graphify'}):
        needed.append('uv')
    if (requested.intersection({'codex', 'openspec'}) or any('shadcn' in values for values in plan.mcp.values())) and not shutil.which('npm'):
        needed.append('vp')
    for name in ('openspec', 'graphify'):
        if any(name in values for values in plan.workflows.values()):
            needed.append(name)
            if name == 'graphify':
                needed.append('uv')
            elif not shutil.which('npm'):
                needed.append('vp')
    if any(plan.plugins.values()):
        needed.append('git')
    if plan.github_login or plan.use_profile:
        needed.append('gh')
    if plan.shell_config or plan.git_identity or plan.use_profile:
        needed.append('git')
    plan.dependencies = list(dict.fromkeys(name for name in needed if name not in plan.programs and not detected(name, setup)))
    if args.config_only and (plan.programs or plan.dependencies):
        raise ValueError('Selected actions need missing programs. Run without --config-only, or go back and skip those actions.')


def review(plan, setup):
    from skill_manager import destination
    section('Review / nothing has been changed')
    rows = []
    for name in plan.programs + plan.dependencies:
        existing = detected(name, setup)
        target = str(Path(os.environ.get('UV_PYTHON_INSTALL_DIR', setup.DATA.parent / 'uv/python'))) if name == 'python' else str(setup.BIN)
        rows.append(('Program' + (' prerequisite' if name in plan.dependencies else ''), name, 'Keep installed: ' + existing if existing else 'Install → ' + target))
    rows.append(('Shell configuration', 'Install + backups' if plan.shell_config else 'Skip', str(setup.CONFIG / 'linux-setup') if plan.shell_config else 'No shell files changed'))
    if plan.shell_config:
        rows.append(('Shell startup files', 'Back up existing files, then load managed configuration', ', '.join(str(setup.HOME / name) for name in ('.zshenv', '.zshrc', '.bashrc', '.bash_profile', '.tmux.conf'))))
    for agent in plan.agents:
        rows.append(('Agent / authentication', agent + ' / ' + plan.auth.get(agent, 'skip'), 'Official CLI private credential store / environment'))
        if plan.skills.get(agent):
            rows.append((agent + ' skills', ', '.join(plan.skills[agent]), str(destination(agent, plan.scope, plan.project or None))))
        if plan.mcp.get(agent):
            target = (Path(plan.project) / ('.codex/config.toml' if agent == 'codex' else '.mcp.json')) if plan.scope == 'project' else (Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'config.toml' if agent == 'codex' else (Path(os.environ['CLAUDE_CONFIG_DIR']) / '.claude.json' if os.environ.get('CLAUDE_CONFIG_DIR') else Path.home() / '.claude.json'))
            rows.append((agent + ' MCP', ', '.join(plan.mcp[agent]), str(target)))
        if plan.plugins.get(agent):
            config = (Path(plan.project) / '.claude/settings.json') if plan.scope == 'project' else Path(os.environ.get('CLAUDE_CONFIG_DIR', Path.home() / '.claude')) / 'settings.json'
            repository = json.loads((setup.ROOT / 'skills.catalog.json').read_text())['repositories']['uiux']
            cache = Path(os.environ.get('CLAUDE_CONFIG_DIR', Path.home() / '.claude')) / 'plugins'
            rows.append(('Claude native plugin', repository['repo'] + '#' + repository['commit'] + '; keep existing', str(config) + '; cache: ' + str(cache)))
        if plan.workflows.get(agent):
            rows.append((agent + ' project workflows', ', '.join(plan.workflows[agent]), plan.workflow_project + ' / generated agent skills and commands'))
    if plan.git_identity:
        rows.append(('Global Git author', plan.git_identity['name'] + ' <' + plan.git_identity['email'] + '>', str(Path(os.environ.get('GIT_CONFIG_GLOBAL', Path.home() / '.gitconfig')))))
    if plan.github_login:
        rows.append(('GitHub sign-in', 'Browser authentication', 'GitHub CLI private credential store'))
    if plan.profiles:
        import git_profiles
        for item in plan.profiles:
            rows.append(('Saved GitHub profile', item['username'] + ': ' + item['name'] + ' <' + item['email'] + '>', str(git_profiles.profiles_path())))
    if plan.use_profile:
        rows.append(('Project GitHub profile', plan.use_profile, plan.profile_project + ' / .git/config; active gh account'))
    table(('Selection', 'Action', 'Destination'), rows)
    print('Existing tools, skills, and MCP servers are kept. Project MCP backups: ' + str(setup.STATE / 'backups') + '.')
    print('Integration hierarchy: skills → agent skill folder; MCP → scoped config; workflows → project folder.')


def collect(setup, lock, args):
    plan = Plan()
    pages = [programs_page, agents_page, scope_page, integrations_page, git_page]
    index = 0
    while True:
        try:
            if index < len(pages):
                section(f'Setup wizard / {index + 1} of {len(pages)}')
                print('Arrows: move | Space: select multiple | Enter: accept | Esc: back | Ctrl-S: skip | Ctrl-X/C: cancel')
                before = deepcopy(plan)
                try:
                    pages[index](plan, setup, lock, args)
                except (Back, ValueError):
                    plan = before
                    raise
                index += 1
            else:
                resolve_dependencies(plan, setup, args)
                review(plan, setup)
                choice = pick('Apply this plan?', [('Apply selected changes', 'apply'), ('Edit selections', 'edit'), ('Cancel without changes', 'cancel')], default=1, skip=False)
                if choice == 'apply':
                    return plan
                if choice == 'cancel':
                    return None
                index = 0
        except Back:
            if index == 0:
                return None
            index -= 1
        except ValueError as error:
            status('warn', str(error))
            if index == len(pages):
                index = 0


def run_command(command, **kwargs):
    subprocess.run(command, check=True, **kwargs)


def execute(plan, setup, lock, key):
    """The only mutating wizard entry point; called after final review."""
    import dev_tools
    import git_profiles
    from agent_integrations import configure, install_uiux_plugin
    from skill_manager import destination, install_skill
    from preflight import check
    programs = list(dict.fromkeys(plan.programs + plan.dependencies))
    missing = [name for name in programs if not detected(name, setup)]
    base = [name for name in missing if name in setup.BASE]
    selected_lock = {**lock, 'tools': {name: item for name, item in lock['tools'].items() if name in missing}, 'plugins': {name: item for name, item in lock['plugins'].items() if name in missing}}
    # Preflight checks only the selected programs and their displayed dependencies.
    for message in check(setup.ROOT, setup.CONFIG, setup.DATA, setup.STATE, setup.CACHE, setup.BIN,
                         config_only=plan.shell_config and not base and not selected_lock['tools'], network=bool(missing),
                         selected_base=base, require_vp='vp' in missing):
        status('info', message)
    with setup.operation_lock():
        setup.migrate_legacy()
        deploy = setup.Deployment()
        actions = []
        if base:
            actions.append(('selected base programs', lambda: setup.install_base(deploy, selected=base)))
        if selected_lock['tools'] or selected_lock['plugins']:
            actions.append(('selected tools and plugins', lambda: setup.install_tools(selected_lock, key, deploy)))
        if 'gh' in missing:
            actions.append(('GitHub CLI', lambda: setup.install_gh(lock, key, deploy)))
        if plan.shell_config:
            actions.append(('shell configuration', lambda: setup.install_config(deploy)))
        dev = [name for name in missing if name in DEV]
        if dev:
            actions.append(('selected developer tools', lambda: dev_tools.install(selected=dev)))
        for agent in plan.agents:
            method = plan.auth.get(agent, 'skip')
            if method != 'skip':
                actions.append((agent + ' authentication', lambda agent=agent, method=method: dev_tools.authenticate(agent, method=method)))
            if plan.mcp.get(agent):
                actions.append((agent + ' MCP servers', lambda agent=agent: configure(agent, plan.mcp[agent], plan.scope, plan.project, deploy.backup_dir)))
            for skill in plan.skills.get(agent, []):
                def add_skill(agent=agent, skill=skill):
                    catalog = json.loads((setup.ROOT / 'skills.catalog.json').read_text())
                    item = next(item for item in catalog['skills'] if item['id'] == skill)
                    target = destination(agent, plan.scope, plan.project or None)
                    if plan.scope == 'project' and not target.resolve().is_relative_to(Path(plan.project).resolve()):
                        raise RuntimeError('Skill destination resolves outside the selected project; existing links were kept')
                    with tempfile.TemporaryDirectory(prefix='linux-skills-') as temporary:
                        install_skill(item, catalog['repositories'][item['repository']], target, temporary)
                actions.append((agent + ' skill / ' + skill, add_skill))
            if plan.plugins.get(agent):
                catalog = json.loads((setup.ROOT / 'skills.catalog.json').read_text())
                actions.append(('Claude native UI/UX plugin', lambda: install_uiux_plugin(plan.scope, plan.project, catalog['repositories']['uiux'])))
            for workflow in plan.workflows.get(agent, []):
                command = [workflow, 'init', '--tools', agent] if workflow == 'openspec' else [workflow, agent, 'install', '--project']
                actions.append((agent + ' workflow / ' + workflow, lambda command=command: run_command(command, cwd=plan.workflow_project)))
        if plan.git_identity:
            def identity():
                for field, value in plan.git_identity.items():
                    subprocess.run(['git', 'config', '--global', 'user.' + field, value], check=True)
            actions.append(('global Git identity', identity))
        if plan.github_login:
            actions.append(('GitHub authentication', lambda: run_command(['gh', 'auth', 'login', '--web'])))
        if plan.profiles:
            def save_profiles():
                profiles = git_profiles.load_profiles()
                for profile in plan.profiles:
                    profiles.setdefault(profile['username'], {key: profile[key] for key in ('name', 'email')})
                git_profiles.save_profiles(profiles)
            actions.append(('saved GitHub profiles', save_profiles))
        if plan.use_profile:
            def use_profile():
                profiles = git_profiles.load_profiles()
                subprocess.run(['gh', 'auth', 'switch', '--hostname', 'github.com', '--user', plan.use_profile], check=True)
                for field in ('name', 'email'):
                    subprocess.run(['git', '-C', plan.profile_project, 'config', '--local', 'user.' + field, profiles[plan.use_profile][field]], check=True)
            actions.append(('project GitHub profile', use_profile))
        journal = setup.InstallationRun(deploy, 'wizard', total=len(actions))
        for name, action in actions:
            journal.step(name, action)
        failures = journal.finish()
    status('warn' if failures else 'ok', 'Rerun ./install.sh to review and retry incomplete selections.' if failures else 'Selected setup actions completed.')
    if plan.shell_config:
        from next_steps import print_guide
        zsh = setup.find_tool('zsh')
        if zsh:
            print('Run: exec ' + shlex.quote(zsh) + '\nThen: doctor')
        print_guide(zsh)
    return 1 if failures else 0


def run(setup, lock, key, args):
    try:
        plan = collect(setup, lock, args)
    except (KeyboardInterrupt, EOFError):
        status('info', 'Setup cancelled; no files were changed.')
        return 0
    if plan is None:
        status('info', 'Setup cancelled; no files were changed.')
        return 0
    agent_actions = any(plan.auth.get(agent, 'skip') != 'skip' or plan.skills.get(agent) or plan.mcp.get(agent) or plan.plugins.get(agent) or plan.workflows.get(agent) for agent in plan.agents)
    installs = any(not detected(name, setup) for name in plan.programs + plan.dependencies)
    if not (installs or plan.shell_config or agent_actions or plan.git_identity or plan.github_login or plan.profiles or plan.use_profile):
        status('info', 'Nothing to apply; installed programs are kept and no files were changed.')
        return 0
    return execute(plan, setup, lock, key)
