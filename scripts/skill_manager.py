#!/usr/bin/env python3
"""Browse, install, and remove local skills for Codex and Claude Code."""
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from terminal_ui import choose, choose_many, confirm

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "skills.catalog.json"
AGENTS = {"codex": "Codex", "claude": "Claude Code"}
MAX_ARCHIVE = 150 * 1024 * 1024
MAX_SKILL = 80 * 1024 * 1024


def destination(agent, scope, project=None):
    if agent not in AGENTS or scope not in ("global", "project"):
        raise ValueError("Unsupported agent or scope")
    if scope == "global":
        return Path.home() / (".agents/skills" if agent == "codex" else ".claude/skills")
    if not project or not Path(project).expanduser().is_dir():
        raise ValueError("Project path must be an existing directory")
    return Path(project).expanduser().resolve() / (".agents/skills" if agent == "codex" else ".claude/skills")


def get_archive(repository, commit, directory):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid catalog repository or commit")
    archive = Path(directory) / (repository.replace("/", "--") + ".tar.gz")
    if archive.exists():
        return archive
    request = urllib.request.Request(f"https://codeload.github.com/{repository}/tar.gz/{commit}", headers={"User-Agent": "linux-setup/1"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response, archive.open("wb") as out:
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ARCHIVE:
                    raise ValueError("Skill archive exceeds the download limit")
                out.write(chunk)
    except BaseException:
        archive.unlink(missing_ok=True)
        raise
    return archive


def unpack_skill(archive, item, stage):
    """Copy regular files from exactly one skill directory, without following links."""
    prefix = PurePosixPath(item["path"])
    if prefix.is_absolute() or ".." in prefix.parts:
        raise ValueError("Invalid skill path in catalog")
    seen, total = set(), 0
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            parts = PurePosixPath(member.name).parts
            if len(parts) < 2:
                continue
            relative = PurePosixPath(*parts[1:])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unsafe path in skill archive")
            try:
                target_path = relative.relative_to(prefix)
            except ValueError:
                continue
            if str(target_path) == "." or member.isdir():
                continue
            if item.get("root_files") and str(target_path) not in item["root_files"]:
                continue
            if not member.isfile() or str(target_path) in seen:
                raise ValueError(f"Unsafe or duplicate skill file: {target_path}")
            seen.add(str(target_path))
            total += member.size
            if total > MAX_SKILL:
                raise ValueError("Skill exceeds the extracted size limit")
            target = stage.joinpath(*target_path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.extractfile(member) as source, target.open("wb") as out:
                shutil.copyfileobj(source, out)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)
    if not (stage / "SKILL.md").is_file():
        raise ValueError("Selected source does not contain SKILL.md")


def install_skill(item, repository, root, temp):
    name = item["id"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        raise ValueError("Invalid skill name in catalog")
    target = root / name
    if target.exists() or target.is_symlink():
        print(f"Keeping existing skill: {target}")
        return False
    print(f"Downloading {name} from https://github.com/{repository['repo']} at {repository['commit']} ...", flush=True)
    archive = get_archive(repository["repo"], repository["commit"], temp)
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".linux-skill-stage-", dir=root) as staged:
        stage = Path(staged) / "payload"
        stage.mkdir()
        unpack_skill(archive, item, stage)
        if item.get("adapt_uiux"):
            skill = stage / "SKILL.md"
            text = skill.read_text()
            old = '${CLAUDE_PLUGIN_ROOT}/.claude/skills/ui-ux-pro-max'
            if old not in text:
                raise ValueError("UI/UX Pro Max path format changed; catalog needs review")
            escaped = str(target).replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')
            skill.write_text(text.replace(old, escaped))
        if target.exists() or target.is_symlink():
            print(f"Keeping existing skill: {target}")
            return False
        try:
            stage.rename(target)
        except OSError:
            if target.exists() or target.is_symlink():
                print(f"Keeping existing skill: {target}")
                return False
            raise
    print(f"Installed {name}: {target}")
    return True


def list_installed(root):
    if not root.is_dir():
        return []
    return sorted((p for p in root.iterdir() if not p.name.startswith('.') and p.is_dir() and (p / 'SKILL.md').is_file()), key=lambda p: p.name.lower())


def remove_skills(root):
    installed = list_installed(root)
    if not installed:
        print(f"No skills found in {root}.")
        return
    selected = choose_many("Select installed skills to remove", [p.name + (" (symlink; target kept)" if p.is_symlink() else "") for p in installed])
    if not selected:
        return
    chosen = [installed[i] for i in selected]
    print("The following skill directories will be deleted:")
    for path in chosen:
        print("  " + str(path))
    if confirm("Remove these skills?"):
        for path in chosen:
            if path.is_symlink():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
            else:
                print(f"Skipping changed path: {path}")
                continue
            print(f"Removed {path.name}")


def install_menu(catalog, agent, root):
    available = [item for item in catalog['skills'] if agent in item['agents']]
    areas = sorted({area for item in available for area in item['areas']})
    selected_areas = choose_many("Choose your work areas (select one or more)", areas + ["All skills"])
    if not selected_areas:
        return
    chosen_areas = {areas[index] for index in selected_areas if index < len(areas)}
    entries = available if len(areas) in selected_areas else [item for item in available if chosen_areas.intersection(item['areas'])]
    labels = [f"{item['id']} — {item['description']} ({catalog['repositories'][item['repository']]['repo']})" for item in entries]
    selected = choose_many("Select skills to install", labels)
    if not selected:
        return
    print(f"Destination: {root}")
    print("Skills are third-party instructions and may include scripts. Review their sources before use.")
    for i in selected:
        item = entries[i]
        repo = catalog['repositories'][item['repository']]
        print(f"  {item['id']}: https://github.com/{repo['repo']}/tree/{repo['commit']}/{item['path']}")
    if not confirm("Install these skills?"):
        return
    failures = []
    with tempfile.TemporaryDirectory(prefix="linux-skills-download-") as temp:
        for i in selected:
            item = entries[i]
            try:
                install_skill(item, catalog['repositories'][item['repository']], root, temp)
            except (OSError, ValueError, tarfile.TarError) as error:
                failures.append(root / item["id"])
                print(f"Could not install {item['id']}: {error}", file=sys.stderr)
    print("Restart your agent session if it does not discover new skills immediately.")
    return failures


def main():
    if not sys.stdin.isatty():
        print("skill-manager requires an interactive terminal.", file=sys.stderr)
        return 1
    catalog = json.loads(CATALOG.read_text())
    failed = set()
    while True:
        action = choose("AI skill manager", ["Install skills", "Review or remove installed skills", "Exit"])
        if action is None or action == 2:
            unresolved = sorted(path for path in failed if not (path / "SKILL.md").is_file())
            if unresolved:
                print("Incomplete skills: " + ", ".join(map(str, unresolved)) + ". Rerun skill-manager to retry.", file=sys.stderr)
            return 1 if unresolved else 0
        agent_index = choose("Choose your AI agent", list(AGENTS.values()) + ["Back"])
        if agent_index is None or agent_index == len(AGENTS):
            continue
        agent = list(AGENTS)[agent_index]
        while True:
            scope = choose("Choose the scope", ["Global (all projects)", "Project", "Back"])
            if scope is None or scope == 2:
                break
            project = None
            if scope == 1:
                project = input("Existing project directory (absolute path, or . for current directory; blank goes back): ").strip()
                if not project:
                    continue
            try:
                root = destination(agent, "global" if scope == 0 else "project", project)
            except ValueError as error:
                print(error)
                continue
            print(f"Skill directory: {root}")
            if action == 0:
                failed.update(install_menu(catalog, agent, root) or [])
            else:
                remove_skills(root)
            break


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        sys.exit(130)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"skill-manager: {error}", file=sys.stderr)
        sys.exit(1)
