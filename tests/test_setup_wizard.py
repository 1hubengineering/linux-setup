"""Planning must be read-only; application must honor scope and selected tools."""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import setup_wizard as wizard
import agent_integrations
import dev_tools


def load_setup():
    spec = importlib.util.spec_from_file_location('wizard_setup_test', ROOT / 'scripts/setup.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WizardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.setup = load_setup()
        for key, value in [('HOME', self.home), ('CONFIG', self.home / 'config'), ('DATA', self.home / 'data'), ('STATE', self.home / 'state'), ('CACHE', self.home / 'cache'), ('BIN', self.home / 'bin')]:
            item = patch.object(self.setup, key, value)
            item.start()
            self.addCleanup(item.stop)
        env = patch.dict(os.environ, {'HOME': str(self.home), 'XDG_CONFIG_HOME': str(self.home / 'config'), 'CI': ''})
        env.start()
        self.addCleanup(env.stop)
        self.args = SimpleNamespace(config_only=False, dev_tools=False, auth=False, skip_mcp=False)
        self.lock = json.loads((ROOT / 'tools.lock.json').read_text())

    def test_cancelling_first_page_creates_no_files_or_state(self):
        with patch.object(wizard, 'pick', side_effect=wizard.Back), patch.object(self.setup, 'operation_lock') as lock, patch.object(self.setup, 'Deployment') as deployment:
            self.assertEqual(wizard.run(self.setup, self.lock, 'linux-x86_64', self.args), 0)
        lock.assert_not_called()
        deployment.assert_not_called()
        self.assertEqual(list(self.home.iterdir()), [])

    def test_review_cancel_after_all_choices_remains_read_only(self):
        # No programs, no shells, no agents, no Git actions; then cancel review.
        with patch.object(wizard, 'pick', side_effect=['skip', False, [], [], 'cancel']), patch.object(self.setup, 'operation_lock') as lock, patch.object(wizard.subprocess, 'run') as command:
            self.assertIsNone(wizard.collect(self.setup, self.lock, self.args))
        command.assert_not_called()
        lock.assert_not_called()
        self.assertEqual(list(self.home.iterdir()), [])

    def test_skip_all_then_apply_is_a_noop(self):
        with patch.object(wizard, 'pick', side_effect=['skip', False, [], [], 'apply']), patch.object(wizard, 'execute') as execute:
            self.assertEqual(wizard.run(self.setup, self.lock, 'linux-x86_64', self.args), 0)
        execute.assert_not_called()
        self.assertEqual(list(self.home.iterdir()), [])

    def test_keeping_installed_agents_without_other_actions_does_not_create_state(self):
        plan = wizard.Plan(agents=['codex'], auth={'codex': 'skip'}, shell_config=False)
        with patch.object(wizard, 'collect', return_value=plan), patch.object(wizard, 'execute') as execute:
            self.assertEqual(wizard.run(self.setup, self.lock, 'linux-x86_64', self.args), 0)
        execute.assert_not_called()
        self.assertEqual(list(self.home.iterdir()), [])

    def test_escape_returns_to_previous_page_instead_of_applying(self):
        with patch.object(wizard, 'pick', side_effect=['skip', False, wizard.Back, wizard.Back]), patch.object(wizard, 'execute') as execute:
            self.assertIsNone(wizard.collect(self.setup, self.lock, self.args))
        execute.assert_not_called()
        self.assertEqual(list(self.home.iterdir()), [])

    def test_dependencies_are_explicit_and_unrelated_programs_are_not_added(self):
        plan = wizard.Plan(programs=['graphify'], shell_config=False)
        with patch.object(wizard, 'detected', return_value=None):
            wizard.resolve_dependencies(plan, self.setup, self.args)
        self.assertEqual(plan.dependencies, ['uv'])
        self.assertNotIn('codex', plan.dependencies)
        self.assertNotIn('vp', plan.dependencies)

    def test_deselecting_agent_removes_its_implied_installation(self):
        plan = wizard.Plan(agents=['codex'], agents_visited=True, shell_config=False)
        with patch.object(wizard, 'detected', return_value=None), patch.object(wizard, 'pick', return_value=[]):
            wizard.agents_page(plan, self.setup, self.lock, self.args)
            wizard.resolve_dependencies(plan, self.setup, self.args)
        self.assertEqual(plan.agents, [])
        self.assertEqual(plan.programs, [])
        self.assertEqual(plan.dependencies, [])

    def test_previously_cleared_agent_selection_is_not_reselected(self):
        plan = wizard.Plan(agents=[], agents_visited=True)
        with patch.object(wizard, 'detected', return_value='/installed/agent'), patch.object(wizard, 'pick', return_value=[]) as pick:
            wizard.agents_page(plan, self.setup, self.lock, self.args)
        self.assertEqual(pick.call_args.kwargs['selected'], [])

    def test_config_only_rejects_required_downloads(self):
        plan = wizard.Plan(programs=['graphify'], shell_config=False)
        self.args.config_only = True
        with patch.object(wizard, 'detected', return_value=None), self.assertRaises(ValueError):
            wizard.resolve_dependencies(plan, self.setup, self.args)

    def test_installed_selected_programs_are_not_reinstalled(self):
        plan = wizard.Plan(programs=['codex'], shell_config=False)
        with patch.object(wizard, 'detected', return_value='/existing/codex'), patch('preflight.check', return_value=[]), patch.object(dev_tools, 'install') as install, patch.object(self.setup, 'install_base') as base, patch.object(self.setup, 'install_tools') as tools, patch.object(self.setup, 'install_config') as config:
            self.assertEqual(wizard.execute(plan, self.setup, self.lock, 'linux-x86_64'), 0)
        install.assert_not_called()
        base.assert_not_called()
        tools.assert_not_called()
        config.assert_not_called()

    def test_only_selected_developer_cli_is_installed(self):
        plan = wizard.Plan(programs=['claude'], shell_config=False)
        with patch.object(wizard, 'detected', return_value=None), patch('preflight.check', return_value=[]), patch.object(dev_tools, 'install', return_value=[]) as install, patch.object(self.setup, 'install_config') as config:
            self.assertEqual(wizard.execute(plan, self.setup, self.lock, 'linux-x86_64'), 0)
        install.assert_called_once_with(selected=['claude'])
        config.assert_not_called()

    def test_project_workflow_command_cannot_write_global_graphify_settings(self):
        plan = wizard.Plan(agents=['codex'], shell_config=False, workflows={'codex': ['graphify']}, workflow_project=str(self.home))
        with patch('preflight.check', return_value=[]), patch.object(wizard.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            self.assertEqual(wizard.execute(plan, self.setup, self.lock, 'linux-x86_64'), 0)
        run.assert_called_once_with(['graphify', 'codex', 'install', '--project'], cwd=str(self.home), check=True)

    def test_saved_profiles_do_not_change_global_git_identity_or_existing_profiles(self):
        import git_profiles
        original = {'existing': {'name': 'Original', 'email': 'original@example.test'}}
        git_profiles.save_profiles(original)
        plan = wizard.Plan(shell_config=False, profiles=[{'username': 'existing', 'name': 'Replacement', 'email': 'changed@example.test'}, {'username': 'additional', 'name': 'New Author', 'email': 'new@example.test'}])
        with patch('preflight.check', return_value=[]), patch.object(wizard.subprocess, 'run') as commands:
            self.assertEqual(wizard.execute(plan, self.setup, self.lock, 'linux-x86_64'), 0)
        commands.assert_not_called()
        self.assertEqual(git_profiles.load_profiles()['existing'], original['existing'])
        self.assertIn('additional', git_profiles.load_profiles())
        self.assertFalse((self.home / '.gitconfig').exists())

    def test_planning_interrupt_is_a_clean_no_change_cancellation(self):
        with patch.object(wizard, 'collect', side_effect=KeyboardInterrupt), patch.object(wizard, 'execute') as execute:
            self.assertEqual(wizard.run(self.setup, self.lock, 'linux-x86_64', self.args), 0)
        execute.assert_not_called()
        self.assertEqual(list(self.home.iterdir()), [])

    def test_scope_destinations_are_shown_before_application(self):
        plan = wizard.Plan(agents=['codex', 'claude'], scope='project', project=str(self.home), shell_config=False, skills={'codex': ['shadcn']}, mcp={'codex': ['shadcn'], 'claude': ['better-auth']})
        with patch.object(sys, 'stdout', new_callable=io.StringIO) as output:
            wizard.review(plan, self.setup)
        value = output.getvalue().replace('\n', '')
        self.assertIn('.agents/skills', value)
        self.assertIn('.codex/config.toml', value)
        self.assertIn('.mcp.json', value)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_default_interactive_route_does_not_acquire_lock_before_wizard(self):
        with patch.object(sys, 'argv', ['setup.py']), patch.object(sys.stdin, 'isatty', return_value=True), patch.object(sys.stdout, 'isatty', return_value=True), patch.object(self.setup, '_main', return_value=0), patch.object(self.setup, 'operation_lock') as lock:
            self.assertEqual(self.setup.main(), 0)
        lock.assert_not_called()

    def test_explicit_wizard_noninteractive_fails_before_state(self):
        with patch.object(sys, 'argv', ['setup.py', '--wizard']), patch.object(sys.stdin, 'isatty', return_value=False), self.assertRaises(RuntimeError):
            self.setup.main()
        self.assertEqual(list(self.home.iterdir()), [])


class ScopedMcpTests(unittest.TestCase):
    def test_project_json_preserves_existing_servers_and_reuses_them_on_rerun(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / '.mcp.json'
            original = {'mcpServers': {'shadcn': {'command': 'my-custom-shadcn'}}, 'extra': {'kept': True}}
            config.write_text(json.dumps(original))
            backups = root / 'backups'
            agent_integrations.configure('claude', ['shadcn', 'better-auth'], 'project', root, backups)
            data = json.loads(config.read_text())
            self.assertEqual(data['mcpServers']['shadcn'], original['mcpServers']['shadcn'])
            self.assertEqual(data['extra'], {'kept': True})
            before = config.read_bytes()
            agent_integrations.configure('claude', ['shadcn', 'better-auth'], 'project', root, backups)
            self.assertEqual(before, config.read_bytes())
            self.assertEqual(len(list(backups.iterdir())), 1)
            self.assertEqual(list(backups.iterdir())[0].stat().st_mode & 0o777, 0o600)

    def test_project_toml_adds_selected_servers_together(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            agent_integrations.configure('codex', ['shadcn', 'better-auth'], 'project', root, root / 'backups')
            config = root / '.codex/config.toml'
            self.assertIn('[mcp_servers."shadcn"]', config.read_text())
            self.assertIn('[mcp_servers."better-auth"]', config.read_text())
            if sys.version_info >= (3, 11):
                before = config.read_bytes()
                agent_integrations.configure('codex', ['shadcn', 'better-auth'], 'project', root, root / 'backups')
                self.assertEqual(config.read_bytes(), before)
                self.assertFalse((root / 'backups').exists())

    def test_invalid_config_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / '.mcp.json'
            config.write_text('{broken')
            with self.assertRaises(ValueError):
                agent_integrations.configure('claude', ['shadcn'], 'project', root, root / 'backups')
            self.assertEqual(config.read_text(), '{broken')
            self.assertFalse((root / 'backups').exists())

    def test_project_plugin_uses_pinned_source_and_project_settings(self):
        repo = {'repo': 'nextlevelbuilder/ui-ux-pro-max-skill', 'commit': 'a' * 40}
        with patch.object(agent_integrations.subprocess, 'run', return_value=Mock(returncode=0, stdout='[]')) as run:
            agent_integrations.install_uiux_plugin('project', '/project', repo)
        self.assertEqual(run.call_count, 3)
        self.assertIn(repo['repo'] + '#' + repo['commit'], run.call_args_list[1].args[0])
        self.assertEqual(run.call_args_list[1].args[0][-2:], ['--scope', 'project'])
        self.assertEqual(run.call_args.args[0][-2:], ['--scope', 'project'])
        self.assertTrue(all(call.kwargs['cwd'] == '/project' for call in run.call_args_list))

    def test_conflicting_existing_plugin_marketplace_is_kept(self):
        market = [{'name': 'ui-ux-pro-max-skill', 'repo': 'someone/else'}]
        with patch.object(agent_integrations.subprocess, 'run', return_value=Mock(returncode=0, stdout=json.dumps(market))) as run:
            with self.assertRaises(RuntimeError):
                agent_integrations.install_uiux_plugin('global', '', {'repo': 'nextlevelbuilder/ui-ux-pro-max-skill', 'commit': 'a' * 40})
        self.assertEqual(run.call_count, 1)

    def test_global_inspection_error_never_adds_server(self):
        with patch.object(agent_integrations.shutil, 'which', return_value='/bin/codex'), patch.object(agent_integrations.subprocess, 'run', return_value=Mock(returncode=1, stdout='', stderr='config parse error')) as run:
            with self.assertRaises(RuntimeError):
                agent_integrations.configure('codex', ['shadcn'], 'global', '', Path('/unused'))
        self.assertEqual(run.call_count, 1)


if __name__ == '__main__':
    unittest.main()
