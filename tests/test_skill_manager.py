import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('skill_manager', ROOT / 'scripts/skill_manager.py')
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)


class SkillManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def archive(self, files):
        archive = self.root / 'source.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            for name, payload in files.items():
                member = tarfile.TarInfo(name)
                if payload is None:
                    member.type = tarfile.SYMTYPE
                    member.linkname = '/etc/passwd'
                    tar.addfile(member)
                else:
                    contents = payload.encode()
                    member.size = len(contents)
                    tar.addfile(member, io.BytesIO(contents))
        return archive

    def test_agent_and_project_locations(self):
        with patch.object(manager.Path, 'home', return_value=self.root):
            self.assertEqual(manager.destination('codex', 'global'), self.root / '.agents/skills')
            self.assertEqual(manager.destination('claude', 'global'), self.root / '.claude/skills')
        self.assertEqual(manager.destination('codex', 'project', self.root), self.root / '.agents/skills')
        self.assertEqual(manager.destination('claude', 'project', self.root), self.root / '.claude/skills')
        with self.assertRaises(ValueError):
            manager.destination('codex', 'project', self.root / 'missing')

    def test_install_copies_support_files_and_does_not_replace_existing(self):
        archive = self.archive({'repo/skills/demo/SKILL.md': '---\nname: demo\n---', 'repo/skills/demo/scripts/tool.py': 'print(1)'})
        item = {'id': 'demo', 'path': 'skills/demo'}
        target = self.root / 'skills'
        with patch.object(manager, 'get_archive', return_value=archive) as fetch:
            self.assertTrue(manager.install_skill(item, {'repo': 'org/repo', 'commit': 'a' * 40}, target, self.root))
            self.assertEqual((target / 'demo/scripts/tool.py').read_text(), 'print(1)')
            (target / 'demo/SKILL.md').write_text('my version')
            self.assertFalse(manager.install_skill(item, {'repo': 'org/repo', 'commit': 'a' * 40}, target, self.root))
            self.assertEqual(fetch.call_count, 1)
        self.assertEqual((target / 'demo/SKILL.md').read_text(), 'my version')

    def test_uiux_search_paths_point_to_actual_skill(self):
        archive = self.archive({'repo/skill/SKILL.md': 'python "${CLAUDE_PLUGIN_ROOT}/.claude/skills/ui-ux-pro-max/scripts/search.py"'})
        item = {'id': 'ui-ux-pro-max', 'path': 'skill', 'adapt_uiux': True}
        with patch.object(manager, 'get_archive', return_value=archive):
            manager.install_skill(item, {'repo': 'org/repo', 'commit': 'a' * 40}, self.root / 'skills', self.root)
        result = (self.root / 'skills/ui-ux-pro-max/SKILL.md').read_text()
        self.assertIn(str(self.root / 'skills/ui-ux-pro-max/scripts/search.py'), result)
        self.assertNotIn('CLAUDE_PLUGIN_ROOT', result)

    def test_archive_rejects_symlinks_and_traversal(self):
        for files in ({'repo/skill/SKILL.md': 'ok', 'repo/skill/link': None}, {'repo/skill/SKILL.md': 'ok', 'repo/skill/../../outside': 'bad'}):
            with self.subTest(files=files):
                archive = self.archive(files)
                stage = self.root / 'stage'
                stage.mkdir(exist_ok=True)
                with self.assertRaises(ValueError):
                    manager.unpack_skill(archive, {'path': 'skill'}, stage)
                self.assertFalse((self.root / 'outside').exists())

    def test_remove_requires_selection_and_confirmation(self):
        skill = self.root / 'demo'
        skill.mkdir()
        (skill / 'SKILL.md').write_text('my content')
        with patch.object(manager, 'choose_many', return_value=[0]), patch.object(manager, 'confirm', return_value=False):
            manager.remove_skills(self.root)
        self.assertTrue(skill.exists())
        with patch.object(manager, 'choose_many', return_value=[0]), patch.object(manager, 'confirm', return_value=True):
            manager.remove_skills(self.root)
        self.assertFalse(skill.exists())

    def test_remove_symlink_keeps_the_target(self):
        target = self.root / 'actual'
        target.mkdir()
        (target / 'SKILL.md').write_text('keep')
        directory = self.root / 'skills'
        directory.mkdir()
        (directory / 'linked').symlink_to(target, target_is_directory=True)
        with patch.object(manager, 'choose_many', return_value=[0]), patch.object(manager, 'confirm', return_value=True):
            manager.remove_skills(directory)
        self.assertFalse((directory / 'linked').is_symlink())
        self.assertEqual((target / 'SKILL.md').read_text(), 'keep')

    def test_multiple_work_areas_union_skills_without_duplicates(self):
        catalog = {"skills": [
            {"id": "shared", "description": "Shared", "areas": ["Web", "UI"], "agents": ["codex"], "repository": "demo"},
            {"id": "web", "description": "Web", "areas": ["Web"], "agents": ["codex"], "repository": "demo"},
            {"id": "other", "description": "Other", "areas": ["Ops"], "agents": ["codex"], "repository": "demo"},
            {"id": "claude", "description": "Claude", "areas": ["Web"], "agents": ["claude"], "repository": "demo"}],
            "repositories": {"demo": {"repo": "example/demo"}}}
        with patch.object(manager, "choose_many", side_effect=[[1, 2], []]) as pick:
            manager.install_menu(catalog, "codex", self.root)
        labels = pick.call_args_list[1].args[1]
        self.assertEqual(len(labels), 2)
        self.assertTrue(labels[0].startswith("shared"))
        self.assertTrue(labels[1].startswith("web"))

    def test_catalog_pins_repositories_and_valid_skill_paths(self):
        catalog = json.loads(manager.CATALOG.read_text())
        ids = set()
        for item in catalog['skills']:
            self.assertNotIn(item['id'], ids)
            ids.add(item['id'])
            self.assertTrue(set(item['agents']) <= set(manager.AGENTS))
            self.assertTrue(item['areas'])
            self.assertNotIn('..', Path(item['path']).parts)
            repo = catalog['repositories'][item['repository']]
            self.assertRegex(repo['commit'], r'^[0-9a-f]{40}$')
        self.assertIn('humanizer', ids)
        self.assertIn('ui-ux-pro-max', ids)


if __name__ == '__main__':
    unittest.main()
