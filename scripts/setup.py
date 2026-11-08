#!/usr/bin/env python3
"""Install pinned terminal tools and link this checkout's configuration."""
import argparse
import ctypes
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ownership import atomic_json, fingerprint, infer_programs, migrate

ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home()
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))
DATA = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share")) / "linux-setup"
STATE = Path(os.environ.get("XDG_STATE_HOME", HOME / ".local/state")) / "linux-setup"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / "linux-setup"
BIN = HOME / ".local/bin"
TOOLS = {"ripgrep": "rg", "oh-my-posh": "oh-my-posh"}
BASE = ["zsh", "tmux", "file", "git", "curl", "lsof", "psql"]


@contextmanager
def operation_lock():
    """One installer/uninstaller may change this user's deployment at a time."""
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with (STATE.parent / ".linux-setup-operation.lock").open("a+") as stream:
        os.chmod(stream.name, 0o600)
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another linux-setup install or uninstall is running. Wait for it to finish, then rerun.") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def find_tool(name):
    """Find managers even before a fresh shell has sourced their environment."""
    executable = shutil.which(name)
    if executable:
        return executable
    candidates = []
    if name == "vp":
        for variable in ["VP_BIN_DIR", "VP_HOME"]:
            if os.environ.get(variable):
                base = Path(os.environ[variable]).expanduser()
                candidates.append(base / ("bin/vp" if variable == "VP_HOME" else "vp"))
        candidates += [DATA.parent / "vite-plus/bin/vp", HOME / ".vite-plus/bin/vp"]
    elif name in ["uv", "uvx"]:
        if os.environ.get("UV_INSTALL_DIR"):
            candidates.append(Path(os.environ["UV_INSTALL_DIR"]).expanduser() / name)
        candidates += [BIN / name, HOME / ".cargo/bin" / name]
    return next((str(p) for p in candidates if p.is_file() and os.access(p, os.X_OK)), None)


def platform_key():
    arch = {"arm64": "aarch64", "amd64": "x86_64"}.get(platform.machine(), platform.machine())
    key = f"{platform.system().lower()}-{arch}"
    if key not in ("linux-x86_64", "linux-aarch64"):
        raise RuntimeError(f"Unsupported platform: {key}. Use Linux on x86_64/ARM64; native Windows and macOS are not supported.")
    return key


def download(url, digest, name):
    """Cache downloads by content, and verify every artifact before using it."""
    target = CACHE / "downloads" / (digest[:16] + "-" + name)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
        return target
    for attempt in range(3):
        temporary = target.with_suffix(target.suffix + ".part")
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "linux-setup/1"})
            with urllib.request.urlopen(request, timeout=90) as response, temporary.open("wb") as out:
                shutil.copyfileobj(response, out)
            actual = hashlib.sha256(temporary.read_bytes()).hexdigest()
            if actual != digest:
                raise RuntimeError(f"Checksum mismatch for {name}: expected {digest}, got {actual}")
            temporary.replace(target)
            return target
        except Exception:
            temporary.unlink(missing_ok=True)
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def extract_executables(archive, destination, names):
    """Read just the requested regular files; never extract archive paths/links."""
    found = set()
    destination.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                name = PurePosixPath(member.filename).name
                if name in names and not member.is_dir():
                    if name in found:
                        raise RuntimeError(f"Duplicate executable in archive: {name}")
                    (destination / name).write_bytes(bundle.read(member))
                    found.add(name)
    else:
        with tarfile.open(archive, "r:*") as bundle:
            for member in bundle:
                name = PurePosixPath(member.name).name
                if name in names and member.isfile():
                    if name in found:
                        raise RuntimeError(f"Duplicate executable in archive: {name}")
                    with bundle.extractfile(member) as source:
                        (destination / name).write_bytes(source.read())
                    found.add(name)
    if found != set(names):
        raise RuntimeError(f"Missing executables in {archive.name}: {set(names) - found}")
    for name in found:
        (destination / name).chmod(0o755)


def extract_plugin(archive, destination, strip_root=True):
    destination.mkdir(parents=True, exist_ok=True)
    links = []
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            parts = PurePosixPath(member.name).parts[1:] if strip_root else PurePosixPath(member.name).parts
            if not parts:
                continue
            if ".." in parts or PurePosixPath(member.name).is_absolute():
                raise RuntimeError("Unsafe path in plugin archive")
            target = destination.joinpath(*parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.extractfile(member) as source:
                    target.write_bytes(source.read())
            elif member.issym():
                links.append((target, member.linkname))
            else:
                raise RuntimeError("Hard links and special files are not supported in plugin archives")
    for target, link in links:
        resolved = (target.parent / link).resolve()
        if not resolved.is_relative_to(destination.resolve()):
            raise RuntimeError("Unsafe symlink in plugin archive")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(link)


def migrate_legacy():
    migrate(sys.modules[__name__] if __name__ in sys.modules else type("Settings", (), globals()))


class Deployment:
    def __init__(self, read_only=False):
        self.read_only = read_only
        self.changed = False
        if not read_only:
            STATE.mkdir(parents=True, exist_ok=True)
        self.path = STATE / "deployment.json"
        legacy = STATE.parent / "dev-setup/deployment.json"
        source = self.path if self.path.exists() else legacy
        self.state = json.loads(source.read_text()) if source.exists() else {"links": {}}
        infer_programs(type("Settings", (), globals()), self.state)
        self.backup_dir = STATE / "backups" / time.strftime("%Y%m%d-%H%M%S")
        finalize_vp(self, save=False)

    def save(self):
        if self.read_only:
            raise RuntimeError("Cannot save a read-only deployment")
        atomic_json(self.path, self.state)

    def record_program(self, name, *, kind="tool", paths=(), shared=(), version="", binaries=(), owned=True, refresh=False, **metadata):
        previous = self.state["programs"].get(name, {})
        # A previously external program is never silently adopted.
        item = {**previous, "owned": owned, "kind": kind, "version": version, "binaries": list(binaries)}
        item["paths"] = sorted(set(previous.get("paths", []) + [str(p) for p in paths])) if owned else []
        item["shared"] = sorted(set(previous.get("shared", []) + [str(p) for p in shared])) if owned else []
        item["fingerprints"] = dict(previous.get("fingerprints", {}))
        for path in paths:
            if refresh or str(path) not in item["fingerprints"]:
                item["fingerprints"][str(path)] = fingerprint(path)
        item.update(metadata)
        self.state["programs"][name] = item
        self.save()

    def link(self, source, target, program=None):
        source, target = Path(source).absolute(), Path(target).absolute()
        if source == target:
            return
        previous = self.state["links"].get(str(target))
        if target.is_symlink() and os.readlink(target) == str(source):
            if previous and (program or previous.get("pending")):
                if program:
                    previous["program"] = program
                for field in ("pending", "before", "replace_owned"):
                    previous.pop(field, None)
                self.save()
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        # Repoint links installed by this repository when the checkout is moved.
        owned = previous and target.is_symlink() and os.readlink(target) == previous["source"]
        pending = previous and previous.get("pending")
        missing = not target.exists() and not target.is_symlink()
        backup = previous.get("backup") if previous and (owned or pending or missing) else None
        if pending and fingerprint(target) not in ("missing", previous["before"]):
            raise RuntimeError(f"Keeping a file changed after an interrupted link: {target}")
        if not pending and not owned and (target.exists() or target.is_symlink()):
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            backup = str(self.backup_dir / (uuid.uuid4().hex + "-" + target.name))
        # Persist the original backup location before moving anything.
        record = {"source": str(source), "backup": backup, "pending": True,
                  "before": fingerprint(target), "replace_owned": bool(owned or (pending and previous.get("replace_owned")))}
        if program:
            record["program"] = program
        self.state["links"][str(target)] = record
        self.save()
        if target.exists() or target.is_symlink():
            if record["replace_owned"]:
                target.unlink()
            else:
                if Path(backup).exists() or Path(backup).is_symlink():
                    raise RuntimeError(f"Backup already exists; keeping {target} and {backup} for review")
                shutil.move(str(target), backup)
        self.changed = True
        target.symlink_to(source, target_is_directory=source.is_dir())
        self.state["links"][str(target)] = {"source": str(source), "backup": backup}
        if program:
            self.state["links"][str(target)]["program"] = program
        self.save()

    def restore(self, targets=None):
        unresolved = []
        for target_name, item in reversed(list(self.state["links"].items())):
            if targets is not None and target_name not in targets:
                continue
            target = Path(target_name)
            missing = not target.exists() and not target.is_symlink()
            if not missing and (not target.is_symlink() or os.readlink(target) != item["source"]):
                print(f"Keeping changed path: {target}")
                unresolved.append(target_name)
                continue
            if not missing:
                target.unlink()
            if item.get("backup") and (Path(item["backup"]).exists() or Path(item["backup"]).is_symlink()):
                shutil.move(item["backup"], str(target))
            del self.state["links"][target_name]
            self.save()
        return unresolved


def install_base(deploy):
    failures = []
    for name in BASE:
        try:
            existing = shutil.which(name)
            legacy = HOME / ".local/share/zsh-runtime"
            if name == "zsh" and existing and legacy in Path(existing).resolve().parents and not Path("/usr/bin/zsh").exists():
                existing = None
            previous = saved_program(deploy, name)
            if existing:
                if not previous:
                    deploy.record_program(name, kind="base", owned=False, binaries=[name], executable=existing)
                print(f"{name}: already installed ({existing}); skipping.", flush=True)
                continue
            folder = DATA / "base" / name
            active = previous.get("pending_bundle", {}).get("path") or previous.get("active_path")
            if active and Path(active).is_relative_to(DATA / "base"):
                folder = Path(active)
            wrapper = folder / "bin" / name
            pending = previous.get("pending_bundle", {})
            if pending.get("path") == str(folder) and pending.get("fingerprint") == fingerprint(folder) and wrapper.is_file():
                record_complete(deploy, name, folder, kind="base", version="distro", binaries=[name])
                previous = saved_program(deploy, name)
            if previous.get("owned") and previous.get("version") == "distro" and wrapper.is_file():
                deploy.link(wrapper, BIN / name, program=name)
                print(f"{name}: already installed; repaired its executable link.", flush=True)
                continue
            if not shutil.which("apt-get"):
                raise RuntimeError(f"Install {name} with your package manager, then rerun ./install.sh")
            requested = "postgresql-client" if name == "psql" else name
            simulation = run(["apt-get", "-s", "--no-install-recommends", "--reinstall", "install", requested], capture_output=True, text=True)
            packages = re.findall(r"^Inst (\S+) \((\S+)", simulation.stdout, re.MULTILINE)
            if not packages:
                raise RuntimeError(f"APT found no downloadable packages for {name}; refresh APT indexes and retry")
            if folder.exists() or folder.is_symlink():
                folder = folder.with_name(folder.name + "-recovered-" + uuid.uuid4().hex[:8])
                print(f"{name}: preserving the incomplete previous directory.", flush=True)
            folder.parent.mkdir(parents=True, exist_ok=True)
            print(f"Installing {name} without sudo ...", flush=True)
            with tempfile.TemporaryDirectory(prefix=".install-", dir=folder.parent) as temporary:
                stage = Path(temporary) / "payload"
                runtime = stage / "runtime"
                runtime.mkdir(parents=True)
                run(["apt-get", "download", *(f"{package}={version}" for package, version in packages)], cwd=temporary)
                archives = sorted(Path(temporary).glob("*.deb"))
                if not archives:
                    raise RuntimeError(f"APT did not download packages for {name}")
                for package in archives:
                    run(["dpkg-deb", "-x", package, runtime])
                write_base_wrapper(name, runtime, stage / "bin", relocate=(stage, folder))
                folder = publish_bundle(stage, folder, deploy, name, "base", "distro", [name])
            record_complete(deploy, name, folder, kind="base", version="distro", binaries=[name], refresh=True, packages=dict(packages))
            deploy.link(folder / "bin" / name, BIN / name, program=name)
        except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
            print(f"{name}: incomplete: {error}. Continuing; rerun ./install.sh to retry.", file=sys.stderr)
            failures.append(name)
            item = deploy.state["programs"].setdefault(name, {"owned": True, "kind": "base", "paths": [], "shared": [], "binaries": [name]})
            item.update(status="incomplete", last_error=str(error))
            deploy.save()
    prepare_retained_zsh(deploy)
    return failures


def write_base_wrapper(name, runtime, wrappers, relocate=None):
    def location(path):
        return relocate[1] / path.relative_to(relocate[0]) if relocate else path

    libraries = [p for p in (runtime / "usr/lib").glob("*-linux-gnu") if p.is_dir()]
    wrappers.mkdir(parents=True, exist_ok=True)
    if name == "psql":
        # Debian's cluster wrapper assumes a system installation.
        choices = sorted((runtime / "usr/lib/postgresql").glob("*/bin/psql"), key=lambda p: int(p.parents[1].name), reverse=True)
    else:
        choices = [runtime / "usr/bin" / name, runtime / "bin" / name, runtime / "usr/sbin" / name]
    binary = next((p for p in choices if p.exists()), None)
    if not binary:
        raise RuntimeError(f"No executable installed for {name}")
    script = "#!/bin/sh\n"
    if libraries:
        prefix = ":".join(str(location(path)) for path in libraries)
        script += f"export LD_LIBRARY_PATH={shlex.quote(prefix)}${{LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}}\n"
    if name == "file":
        magic = next((p for p in [runtime / "usr/lib/file/magic.mgc", runtime / "usr/share/misc/magic.mgc"] if p.is_file() and not p.is_symlink()), None)
        if magic:
            script += f"export MAGIC={shlex.quote(str(location(magic)))}\n"
    if name == "git":
        script += f"export GIT_EXEC_PATH={shlex.quote(str(location(runtime / 'usr/lib/git-core')))}\n"
        script += f"export GIT_TEMPLATE_DIR={shlex.quote(str(location(runtime / 'usr/share/git-core/templates')))}\n"
    if name == "zsh":
        bootstrap = wrappers / "zsh-bootstrap"
        bootstrap.mkdir(exist_ok=True)
        modules = [p for p in (runtime / "usr/lib").glob("*/zsh/*") if p.is_dir()]
        modules += [p for p in (runtime / "usr/lib/zsh").glob("*") if p.is_dir()]
        functions = [p for p in (runtime / "usr/share/zsh/functions").glob("*") if p.is_dir()]
        vendor = Path("/usr/share/zsh/vendor-completions")
        completion_fix = ""
        if vendor.is_dir() and any(p.is_symlink() and not p.exists() for p in vendor.iterdir()):
            clean = bootstrap / "vendor-completions"
            clean.mkdir(exist_ok=True)
            for source in vendor.iterdir():
                target = clean / source.name
                if source.is_file() and not target.exists() and not target.is_symlink():
                    target.symlink_to(source)
            completion_fix = f"fpath=({shlex.quote(str(location(clean)))} ${{fpath:#/usr/share/zsh/vendor-completions}})\n"
        (bootstrap / ".zshenv").write_text(
            "# Runtime support, independent of linux-setup's interactive configuration.\n"
            + "module_path=(" + " ".join(shlex.quote(str(location(p))) for p in modules) + " $module_path)\n"
            + "fpath=(" + " ".join(shlex.quote(str(location(p))) for p in functions) + " $fpath)\n"
            + completion_fix
            + 'ZDOTDIR="${_LINUX_SETUP_USER_ZDOTDIR:-$HOME}"\nunset _LINUX_SETUP_USER_ZDOTDIR\n'
            + '[[ -r "$ZDOTDIR/.zshenv" ]] && source "$ZDOTDIR/.zshenv"\nreturn 0\n')
        script += 'export _LINUX_SETUP_USER_ZDOTDIR="${ZDOTDIR:-$HOME}"\n'
        script += f"export ZDOTDIR={shlex.quote(str(location(bootstrap)))}\n"
    script += f'exec {shlex.quote(str(location(binary)))} "$@"\n'
    wrapper = wrappers / name
    wrapper.write_text(script)
    wrapper.chmod(0o755)
    return wrapper


def prepare_retained_zsh(deploy):
    item = deploy.state["programs"].get("zsh", {})
    wrapper = DATA / "wrappers/zsh"
    if item.get("owned") and wrapper.is_file() and (DATA / "runtime").is_dir():
        checked = [wrapper, DATA / "wrappers/zsh-bootstrap"]
        if any(item.get("fingerprints", {}).get(str(path)) and fingerprint(path) != item["fingerprints"][str(path)] for path in checked):
            print("Keeping modified Zsh wrapper; review standalone runtime support before uninstall.")
            return
        write_base_wrapper("zsh", DATA / "runtime", DATA / "wrappers")
        deploy.record_program("zsh", kind="base", paths=[wrapper, DATA / "wrappers/zsh-bootstrap"],
                              shared=[DATA / "runtime"], binaries=["zsh"], version=item.get("version", "legacy"), refresh=True)


def saved_program(deploy, name):
    return deploy.state["programs"].get(name, {}) if isinstance(deploy.state, dict) else {}


def approve_update(name, version, deploy):
    previous = saved_program(deploy, name)
    installed = previous.get("version")
    if not previous.get("owned") or not installed or installed in (version, "installing", "incomplete"):
        return True
    if previous.get("requested_version") == version:
        print(f"{name}: resuming previously approved update to {version}.", flush=True)
        return True
    print(f"{name}: already installed ({installed}); pinned update available: {version}.", flush=True)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print(f"{name}: keeping installed version. Run ./install.sh interactively to approve the update.", flush=True)
        return False
    from terminal_ui import confirm
    if not confirm(f"Update {name} from {installed} to {version}?"):
        print(f"{name}: update skipped.", flush=True)
        return False
    previous["requested_version"] = version
    deploy.save()
    return True


def repair_program_links(deploy, name):
    """Keep a declined update usable even if an old executable link is missing."""
    for target, item in list(deploy.state["links"].items()):
        if item.get("program") == name and Path(item["source"]).exists():
            deploy.link(item["source"], target, program=name)
    previous = saved_program(deploy, name)
    if previous.get("kind") == "tool" and previous.get("active_path"):
        for binary in previous.get("binaries", []):
            source = Path(previous["active_path"]) / binary
            if source.is_file():
                deploy.link(source, BIN / binary, program=name)


def publish_bundle(stage, destination, deploy, name, kind, version, binaries=()):
    """Publish complete payloads by rename; keep any incomplete old directory."""
    if destination.exists() or destination.is_symlink():
        destination = destination.with_name(destination.name + "-recovered-" + uuid.uuid4().hex[:8])
        print(f"{name}: keeping the previous directory; preparing a complete replacement.", flush=True)
    if isinstance(deploy.state, dict):
        previous = saved_program(deploy, name)
        deploy.record_program(name, kind=kind, paths=[destination], version=previous.get("version", ""),
                              binaries=previous.get("binaries", list(binaries)), status="installing",
                              pending_bundle={"path": str(destination), "fingerprint": fingerprint(stage), "version": version})
    stage.replace(destination)
    deploy.changed = True
    return destination


def record_complete(deploy, name, destination, *, kind="tool", version, binaries=(), refresh=False, **metadata):
    previous = saved_program(deploy, name)
    pending = previous.get("pending_bundle", {})
    if pending.get("path") == str(destination) and pending.get("fingerprint") == fingerprint(destination):
        refresh = True
    deploy.record_program(name, kind=kind, paths=[destination], version=version, binaries=binaries,
                          refresh=refresh, active_path=str(destination), status="complete", **metadata)
    if isinstance(deploy.state, dict):
        item = deploy.state["programs"][name]
        item.pop("pending_bundle", None)
        item.pop("requested_version", None)
        item.pop("last_error", None)
        deploy.save()


def install_one_tool(name, item, key, deploy):
    previous = saved_program(deploy, name)
    existing = find_tool(TOOLS.get(name, name))
    if existing and not previous.get("owned"):
        print(f"{name}: already installed ({existing}); skipping external installation.", flush=True)
        if not previous:
            deploy.record_program(name, owned=False, binaries=item.get("binaries", [TOOLS.get(name, name)]), executable=existing)
        return True
    # Vite+ and uv retain their own supported upgrade workflows.
    if item.get("install_if_missing") and existing:
        active = previous.get("active_path")
        if not active and Path(existing).resolve().is_relative_to(DATA / "tools" / name):
            active = str(Path(existing).resolve().parent)
        if active and Path(active).is_relative_to(DATA / "tools" / name):
            ready = True
            if name == "vp" and (previous.get("setup_incomplete") or not (CONFIG / "vite-plus/env").is_file()):
                print("vp: resuming incomplete runtime setup.", flush=True)
                ready = try_prepare_vp(Path(active) / "vp", deploy)
            for binary in previous.get("binaries", item.get("binaries", [name])):
                source = Path(active) / binary
                if source.is_file():
                    deploy.link(source, BIN / binary, program=name)
            print(f"{name}: already installed ({existing}); skipping download.", flush=True)
            return ready
        print(f"{name}: already installed ({existing}); skipping.", flush=True)
        return True
    if not approve_update(name, item["version"], deploy):
        repair_program_links(deploy, name)
        return True
    asset = item["platforms"].get(key)
    if not asset:
        raise RuntimeError(f"No {name} build for {key}")
    binaries = item.get("binaries", [TOOLS.get(name, name)])
    destination = DATA / "tools" / name / (item["version"] + "-" + key)
    pending = previous.get("pending_bundle", {})
    active = pending.get("path") if pending.get("version") == item["version"] else previous.get("active_path")
    if active and (previous.get("version") == item["version"] or previous.get("pending_bundle", {}).get("version") == item["version"]):
        candidate = Path(active)
        if candidate.is_relative_to(DATA / "tools" / name):
            destination = candidate
    stamp = destination / ".sha256"
    changed = not stamp.is_file() or stamp.read_text().strip() != asset["sha256"] or not all((destination / n).is_file() for n in binaries)
    if changed:
        print(f"Downloading {name} {item['version']} ...", flush=True)
        archive = download(asset["url"], asset["sha256"], asset["name"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".install-", dir=destination.parent) as temporary:
            stage = Path(temporary) / "payload"
            stage.mkdir()
            if item.get("preserve_bundle"):
                extract_plugin(archive, stage, strip_root=False)
                for binary in binaries:
                    (stage / binary).chmod(0o755)
            elif asset["name"].endswith((".tar.gz", ".zip", ".tgz")):
                extract_executables(archive, stage, binaries)
            else:
                shutil.copy2(archive, stage / binaries[0])
                (stage / binaries[0]).chmod(0o755)
            (stage / ".sha256").write_text(asset["sha256"] + "\n")
            destination = publish_bundle(stage, destination, deploy, name, "tool", item["version"], binaries)
    else:
        print(f"{name}: already installed ({item['version']}); skipping download.", flush=True)
    metadata = {}
    if name == "vp" and (changed or not previous or previous.get("pending_bundle")):
        metadata["setup_incomplete"] = True
    record_complete(deploy, name, destination, version=item["version"], binaries=binaries, refresh=changed, **metadata)
    ready = True
    if name == "vp":
        if changed or saved_program(deploy, name).get("setup_incomplete") or not (CONFIG / "vite-plus/env").is_file():
            ready = try_prepare_vp(destination / "vp", deploy)
        if changed:
            deploy.record_program(name, paths=[destination], version=item["version"], binaries=binaries, refresh=True)
    for binary in binaries:
        deploy.link(destination / binary, BIN / binary, program=name)
    return ready


def install_one_plugin(name, item, deploy):
    if not approve_update(name, item["commit"], deploy):
        repair_program_links(deploy, name)
        return
    previous = saved_program(deploy, name)
    destination = DATA / "plugins" / name / item["commit"]
    pending = previous.get("pending_bundle", {})
    active = pending.get("path") if pending.get("version") == item["commit"] else previous.get("active_path")
    if active and (previous.get("version") == item["commit"] or previous.get("pending_bundle", {}).get("version") == item["commit"]):
        candidate = Path(active)
        if candidate.is_relative_to(DATA / "plugins" / name):
            destination = candidate
    stamp = destination / ".sha256"
    changed = not stamp.is_file() or stamp.read_text().strip() != item["sha256"]
    if changed:
        print(f"Downloading {name} {item['version']} ...", flush=True)
        archive = download(item["url"], item["sha256"], name + ".tar.gz")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".install-", dir=destination.parent) as temporary:
            stage = Path(temporary) / "payload"
            extract_plugin(archive, stage)
            (stage / ".sha256").write_text(item["sha256"] + "\n")
            destination = publish_bundle(stage, destination, deploy, name, "plugin", item["commit"])
    else:
        print(f"{name}: already installed; skipping download.", flush=True)
    record_complete(deploy, name, destination, kind="plugin", version=item["commit"], refresh=changed)
    deploy.link(destination, DATA / "plugins" / name / "current", program=name)


def install_tools(lock, key, deploy):
    failures = []
    entries = [(name, item, "tool") for name, item in lock["tools"].items()]
    entries += [(name, item, "plugin") for name, item in lock["plugins"].items()]
    for name, item, kind in entries:
        try:
            if kind == "tool":
                if not install_one_tool(name, item, key, deploy):
                    failures.append("Vite+" if name == "vp" else name)
            else:
                install_one_plugin(name, item, deploy)
        except (OSError, RuntimeError, subprocess.CalledProcessError, tarfile.TarError, zipfile.BadZipFile) as error:
            print(f"{name}: incomplete: {error}. Continuing; rerun ./install.sh to retry.", file=sys.stderr)
            failures.append(name)
            if isinstance(deploy.state, dict):
                program = deploy.state["programs"].setdefault(name, {"owned": True, "kind": kind, "paths": [], "shared": [], "binaries": []})
                program.update(status="incomplete", last_error=str(error))
                deploy.save()
    return failures


def try_prepare_vp(executable, deploy):
    """Allow the rest of setup to finish while recording an incomplete bootstrap."""
    real = isinstance(deploy.state, dict)
    if real:
        if "vp" not in deploy.state["programs"]:
            deploy.record_program("vp", paths=[executable.resolve().parent], binaries=["vp"])
        deploy.state["programs"]["vp"]["setup_incomplete"] = True
        deploy.save()
    try:
        library_dir = ensure_vp_libatomic(deploy)
        prepare_vp(executable, deploy, library_dir=library_dir)
    except (subprocess.CalledProcessError, OSError, RuntimeError) as error:
        print(f"Vite+ setup failed: {error}. Other setup will continue.", file=sys.stderr)
        print(f"Inspect {DATA.parent / 'vite-plus/upgrade.log'} and rerun ./install.sh to retry Vite+.", file=sys.stderr)
        return False
    if real:
        deploy.state["programs"]["vp"].pop("setup_incomplete", None)
        deploy.changed = True
        deploy.save()
    return True


def ensure_vp_libatomic(deploy):
    """Provide Node's libatomic dependency in user space when absent on the host."""
    directory = DATA / "tools/vp/libatomic"
    library = directory / "libatomic.so.1"
    if library.is_file():
        pending = saved_program(deploy, "vp").get("pending_libatomic")
        if pending and pending == fingerprint(directory):
            item = saved_program(deploy, "vp")
            deploy.record_program("vp", paths=[directory], version=item.get("version", ""),
                                  binaries=item.get("binaries", ["vp"]), refresh=True)
            item = saved_program(deploy, "vp")
            item.pop("pending_libatomic", None)
            deploy.save()
        return directory
    try:
        ctypes.CDLL("libatomic.so.1")
        return None
    except OSError:
        pass
    if not shutil.which("apt-get") or not shutil.which("dpkg-deb"):
        raise RuntimeError("Node requires libatomic.so.1; install your distribution's libatomic package and retry")
    print("Installing Node's libatomic dependency without sudo ...", flush=True)
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".install-libatomic-", dir=directory.parent) as temporary:
        stage = Path(temporary)
        run(["apt-get", "download", "libatomic1"], cwd=stage)
        packages = list(stage.glob("*.deb"))
        if len(packages) != 1:
            raise RuntimeError("APT did not download exactly one libatomic1 package")
        extracted = stage / "extracted"
        run(["dpkg-deb", "-x", packages[0], extracted])
        candidates = list(extracted.glob("usr/lib/*/libatomic.so.1")) + list(extracted.glob("lib/*/libatomic.so.1"))
        if len(candidates) != 1 or not candidates[0].is_file():
            raise RuntimeError("libatomic1 package does not contain a usable libatomic.so.1")
        complete = stage / "complete"
        complete.mkdir()
        shutil.copy2(candidates[0].resolve(), complete / library.name)
        if directory.exists() or directory.is_symlink():
            retained = directory.with_name("libatomic-incomplete-" + uuid.uuid4().hex[:8])
            directory.rename(retained)
            print(f"Keeping incomplete library directory at {retained}.", flush=True)
        if isinstance(deploy.state, dict):
            item = deploy.state["programs"]["vp"]
            deploy.record_program("vp", paths=[directory], version=item.get("version", ""),
                                  binaries=item.get("binaries", ["vp"]), pending_libatomic=fingerprint(complete))
        complete.replace(directory)
    if isinstance(deploy.state, dict):
        item = deploy.state["programs"]["vp"]
        deploy.record_program("vp", paths=[directory], version=item.get("version", ""),
                              binaries=item.get("binaries", ["vp"]), refresh=True)
        deploy.state["programs"]["vp"].pop("pending_libatomic", None)
        deploy.save()
    return directory


def prepare_vp(executable, deploy, library_dir=None):
    """Track only changed environment/shim files, never downloaded runtimes."""
    roots = [CONFIG / "vite-plus", DATA.parent / "vite-plus/bin"]
    before = {}
    for root in roots:
        if root.is_dir() and not root.is_symlink():
            for path in root.rglob("*"):
                if path.is_file() or path.is_symlink():
                    before[str(path)] = fingerprint(path)
    # Mock deployments in download tests have no persistent inventory.
    real = isinstance(deploy.state, dict)
    backups = {}
    if real:
        for name, value in before.items():
            path = Path(name)
            backup = deploy.backup_dir / ("vp-" + hashlib.sha256(name.encode()).hexdigest()[:16])
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists() and not backup.is_symlink():
                if path.is_symlink():
                    backup.symlink_to(os.readlink(path))
                else:
                    shutil.copy2(path, backup)
            backups[name] = str(backup)
        deploy.state["programs"]["vp"]["pending_external"] = {"before": before, "backups": backups}
        deploy.save()
    try:
        env = {**os.environ, "VP_SELF_SETUP_NO_MODIFY_PATH": "1", "CI": "1"}
        if library_dir:
            env["LD_LIBRARY_PATH"] = str(library_dir) + (os.pathsep + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
        run([executable, "env", "setup"], env=env)
    finally:
        if real:
            finalize_vp(deploy)


def finalize_vp(deploy, save=True):
    """Account for Vite+ side effects even after failure or a killed installer."""
    item = deploy.state.get("programs", {}).get("vp", {})
    pending = item.get("pending_external")
    if not pending:
        return
    before, backups = pending["before"], pending["backups"]
    current = {}
    for root in [CONFIG / "vite-plus", DATA.parent / "vite-plus/bin"]:
        if root.is_dir() and not root.is_symlink():
            for path in root.rglob("*"):
                if path.is_file() or path.is_symlink():
                    current[str(path)] = fingerprint(path)
    files = item.setdefault("external_files", {})
    for name in sorted(set(before) | set(current)):
        if before.get(name) == current.get(name):
            continue
        path = Path(name)
        backup = files.get(name, {}).get("backup", backups.get(name))
        expected = {"backup": backup}
        if path.is_symlink():
            expected["symlink"] = os.readlink(path)
        elif name in current:
            expected["sha256"] = current[name].removeprefix("file:")
        files[name] = expected
    item.pop("pending_external", None)
    if save:
        deploy.save()


def install_config(deploy):
    # Migrate the known addition from the earlier setup without executing or
    # copying arbitrary shell startup files into a public repository.
    previous_env = HOME / ".zshenv"
    migrate_vite = previous_env.exists() and "vite-plus/env" in previous_env.read_text()
    deploy.link(ROOT, CONFIG / "linux-setup")
    for source, target in [
        ("config/zsh/zshenv", HOME / ".zshenv"),
        ("config/zsh/zshrc", HOME / ".zshrc"),
        ("config/tmux/tmux.conf", HOME / ".tmux.conf"),
        ("config/oh-my-posh", CONFIG / "oh-my-posh"),
        ("config/bat", CONFIG / "bat"),
        ("config/yazi", CONFIG / "yazi"),
        ("config/lazygit", CONFIG / "lazygit"),
    ]:
        deploy.link(ROOT / source, target)
    for script in sorted((ROOT / "bin").iterdir()):
        if script.is_file():
            deploy.link(script, BIN / script.name)
    includes = subprocess.run(["git", "config", "--global", "--get-all", "include.path"], capture_output=True, text=True)
    include = str(CONFIG / "linux-setup/config/git/gitconfig")
    previous_includes = {deploy.state.get("git_include")}
    if str(CONFIG / "dev-setup") in deploy.state["links"]:
        previous_includes.add(str(CONFIG / "dev-setup/config/git/gitconfig"))
    for previous in previous_includes - {None, include}:
        if previous in includes.stdout.splitlines():
            run(["git", "config", "--global", "--fixed-value", "--unset-all", "include.path", previous])
    if include not in includes.stdout.splitlines():
        run(["git", "config", "--global", "--add", "include.path", include])
        deploy.state["git_include"] = include
        deploy.save()
    # Keep local tool initialization outside the portable repository.
    local = CONFIG / "linux-setup-local"
    local.mkdir(parents=True, exist_ok=True)
    for name in ["zshenv", "zshrc"]:
        target = local / name
        if not target.exists():
            target.write_text("# Machine-specific shell additions; never committed to linux-setup.\n")
    if migrate_vite:
        target = local / "zshenv"
        if "vite-plus/env" not in target.read_text():
            with target.open("a") as stream:
                stream.write('\nif [[ -r "$XDG_CONFIG_HOME/vite-plus/env" ]]; then\n  source "$XDG_CONFIG_HOME/vite-plus/env"\nfi\n')
    legacy_history = HOME / ".zsh_history"
    history = STATE.parent / "zsh/history"
    history_marker = STATE / ".history-migrated"
    if legacy_history.is_file() and not history_marker.exists():
        history.parent.mkdir(parents=True, exist_ok=True)
        with history.open("ab") as stream:
            if history.stat().st_size:
                stream.write(b"\n")
            stream.write(legacy_history.read_bytes())
        history_marker.touch()
    # Filter dangling host completions without modifying system directories.
    vendor = Path("/usr/share/zsh/vendor-completions")
    if vendor.is_dir() and any(p.is_symlink() and not p.exists() for p in vendor.iterdir()):
        clean = DATA / "completions/vendor"
        clean.mkdir(parents=True, exist_ok=True)
        for source in vendor.iterdir():
            target = clean / source.name
            if source.is_file() and not target.exists() and not target.is_symlink():
                target.symlink_to(source)


def install_mcp(deploy=None):
    codex = shutil.which("codex")
    if codex:
        deploy = deploy or Deployment()
        existing = subprocess.run([codex, "mcp", "get", "oh-my-posh", "--json"], capture_output=True, text=True)
        if existing.returncode == 0:
            print("Keeping existing Oh My Posh MCP registration.")
            if "mcp" not in deploy.state:
                deploy.state["mcp"] = {"name": "oh-my-posh", "owned": False}
                deploy.save()
            return
        if "No MCP server named" not in existing.stderr and "No MCP server named" not in existing.stdout:
            raise RuntimeError("Could not inspect existing MCP configuration; leaving it unchanged. Use --skip-mcp to continue.")
        run([codex, "mcp", "add", "oh-my-posh", "--url", "https://ohmyposh.dev/api/mcp"])
        created = run([codex, "mcp", "get", "oh-my-posh", "--json"], capture_output=True, text=True)
        digest = hashlib.sha256(json.dumps(json.loads(created.stdout), sort_keys=True).encode()).hexdigest()
        deploy.state["mcp"] = {"name": "oh-my-posh", "url": "https://ohmyposh.dev/api/mcp", "owned": True, "fingerprint": digest}
        deploy.save()
    else:
        print("Codex is not installed; MCP setup skipped. Run ./install.sh --mcp-only after installing Codex.")


def doctor():
    failed = []
    commands = {**{TOOLS.get(n, n): "--version" for n in json.loads((ROOT / "tools.lock.json").read_text())["tools"]},
                "zsh": "--version", "tmux": "-V", "file": "--version", "git": "--version", "psql": "--version"}
    for name, flag in commands.items():
        executable = find_tool(name)
        if not executable:
            print(f"MISSING {name}")
            failed.append(name)
            continue
        result = subprocess.run([executable, flag], capture_output=True, text=True)
        line = (result.stdout or result.stderr).splitlines()
        print(f"{'OK' if result.returncode == 0 else 'FAIL':7} {name:12} {line[0] if line else executable}")
        if result.returncode:
            failed.append(name)
    zsh = shutil.which("zsh")
    if zsh:
        result = subprocess.run([zsh, "-lic", '(( $+functions[_zsh_autosuggest_start] && $+functions[_zsh_highlight] && $+functions[_omp_precmd] && $+functions[z] && $+functions[y] )) && [[ "$POSH_CONFIG" == https://* || -r "$POSH_CONFIG" ]]'], capture_output=True, text=True)
        print("OK      shell integrations" if result.returncode == 0 else "FAIL    shell integrations: " + result.stderr)
        if result.returncode:
            failed.append("shell integrations")
    return 1 if failed else 0


def install_gh(lock, key, deploy):
    return install_tools({"tools": {"gh": lock["optional_tools"]["gh"]}, "plugins": {}}, key, deploy)


def github_setup(lock, key, deploy):
    from git_profiles import add_profiles, ask_yes, configure_identity

    configure_identity()
    if not find_tool("gh"):
        if ask_yes("Install GitHub CLI (gh)?", default=True):
            if install_gh(lock, key, deploy):
                raise RuntimeError("GitHub CLI installation did not finish; rerun ./install.sh --github-setup")
        else:
            print("You can install it later with ./install.sh --install-gh.")
            return
    if any(os.environ.get(name) for name in ("GH_TOKEN", "GITHUB_TOKEN")):
        print("GH_TOKEN or GITHUB_TOKEN is set and can override saved GitHub CLI accounts.")
    if ask_yes("Add a GitHub account and author profile?"):
        add_profiles()
    print("Manage accounts later with git-profile (add, switch, list, or remove).")


def _main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--config-only", action="store_true", help="Link configuration without downloading tools")
    group.add_argument("--check", action="store_true", help="Check tools and shell integrations")
    group.add_argument("--mcp-only", action="store_true", help="Register the Oh My Posh MCP server in Codex")
    group.add_argument("--restore", action="store_true", help="Restore files replaced by this installer")
    group.add_argument("--dry-run", action="store_true", help="Print the install plan without changing anything")
    group.add_argument("--preflight", action="store_true", help="Check prerequisites and network without installing")
    group.add_argument("--install-gh", action="store_true", help="Install GitHub CLI without changing Git identity")
    group.add_argument("--github-setup", action="store_true", help="Set up Git identity and GitHub accounts interactively")
    parser.add_argument("--skip-mcp", action="store_true", help="Do not modify Codex MCP configuration")
    args = parser.parse_args()
    os.environ["PATH"] = str(BIN) + os.pathsep + os.environ.get("PATH", "")
    if args.check:
        return doctor()
    if args.mcp_only:
        platform_key()
        migrate_legacy()
        install_mcp(Deployment())
        return 0
    if args.restore:
        platform_key()
        migrate_legacy()
        deploy = Deployment()
        prepare_retained_zsh(deploy)
        include = deploy.state.pop("git_include", None)
        if include:
            subprocess.run(["git", "config", "--global", "--fixed-value", "--unset-all", "include.path", include], check=False)
            deploy.save()
        deploy.restore(targets=[p for p, item in deploy.state["links"].items() if not item.get("program")])
        print("Restored setup configuration; managed programs and caches were retained.")
        return 0
    key = platform_key()
    lock = json.loads((ROOT / "tools.lock.json").read_text())
    if args.install_gh:
        return 1 if install_gh(lock, key, Deployment()) else 0
    if args.github_setup:
        if not sys.stdin.isatty():
            raise RuntimeError("GitHub setup requires an interactive terminal.")
        github_setup(lock, key, Deployment())
        return 0
    from preflight import check
    cached = all(find_tool(TOOLS.get(name, name)) for name in lock["tools"])
    for message in check(ROOT, CONFIG, DATA, STATE, CACHE, BIN, config_only=args.config_only,
                         network=args.preflight or (not args.config_only and not args.dry_run and not cached)):
        print(message)
    if args.preflight:
        return 0
    if args.dry_run:
        print(f"Platform: {key}\nCheckout: {ROOT}\nConfiguration link: {CONFIG / 'linux-setup'}\nExecutables: {BIN}\nData: {DATA}\nBackups: {STATE / 'backups'}")
        print("Tools:", ", ".join(lock["tools"]))
        print("Plugins:", ", ".join(lock["plugins"]))
        print("Existing programs are kept. Managed tool/plugin updates require interactive confirmation.")
        print("Incomplete work is retried; completed tools and verified downloads are reused.")
        print("Vite+ and uv are installed only when absent; existing installations are kept.")
        print("Base tools use the host package manager; existing files are backed up.")
        return 0
    migrate_legacy()
    deploy = Deployment()
    BIN.mkdir(parents=True, exist_ok=True)
    installation = InstallationRun(deploy, "configuration" if args.config_only else "full")
    if not args.config_only:
        installation.step("base tools", lambda: install_base(deploy))
        installation.step("tools and plugins", lambda: install_tools(lock, key, deploy))
    installation.step("configuration", lambda: install_config(deploy))
    if not args.skip_mcp:
        installation.step("Codex integration", lambda: install_mcp(deploy))
    if not args.config_only and sys.stdin.isatty():
        installation.step("GitHub and skills", lambda: interactive_setup(lock, key, deploy))
    failures = installation.finish()
    if failures:
        print("\nSetup finished with incomplete steps: " + ", ".join(failures), file=sys.stderr)
        print("Rerun ./install.sh to retry; completed tools and backups will be reused.", file=sys.stderr)
    elif not deploy.changed:
        print("\nAlready installed; configuration and executable links checked.")
    else:
        print(f"\nSetup complete from {ROOT}")
    print(f"Backups: {STATE / 'backups'}")
    zsh = shutil.which("zsh")
    if zsh:
        # The calling shell may not yet have ~/.local/bin in its PATH.
        print(f"Run: exec {shlex.quote(zsh)}\nThen: dev-doctor")
    else:
        print("Zsh is not installed. Run ./install.sh without --config-only to install missing tools.")
    from next_steps import print_guide
    print_guide(zsh)
    return 1 if failures else 0


class InstallationRun:
    """Durable step journal; reruns recheck links and reuse completed artifacts."""
    def __init__(self, deploy, mode):
        self.deploy = deploy
        self.failures = []
        self.record = deploy.state.setdefault("installations", {}).setdefault(mode, {"steps": {}})
        if self.record.get("status") in ("running", "incomplete"):
            print("Resuming incomplete setup; completed tools will be kept.", flush=True)
        elif self.record.get("status") == "complete":
            print("Setup is already installed; checking for repairs and approved updates.", flush=True)
        self.record.update(status="running")
        deploy.save()

    def step(self, name, action):
        self.record["current_step"] = name
        self.record["steps"][name] = {"status": "running"}
        self.deploy.save()
        failure_detail = None
        try:
            failures = action() or []
        except (KeyboardInterrupt, EOFError):
            self.record["steps"][name] = {"status": "incomplete", "error": "Interrupted"}
            self.record["status"] = "incomplete"
            self.deploy.save()
            raise
        except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
            print(f"{name}: incomplete: {error}. Continuing with other steps.", file=sys.stderr)
            failures = [name]
            failure_detail = str(error)
        self.record["steps"][name] = {"status": "incomplete" if failures else "complete", "failures": failures}
        if failure_detail:
            self.record["steps"][name]["error"] = failure_detail
        self.failures.extend(failures)
        self.deploy.save()

    def finish(self):
        self.record.update(status="incomplete" if self.failures else "complete", failures=self.failures)
        self.record.pop("current_step", None)
        self.deploy.save()
        return self.failures


def interactive_setup(lock, key, deploy):
    from git_profiles import configure_identity, ask_yes
    configure_identity()
    if not deploy.state.get("github_setup_prompted"):
        github_setup(lock, key, deploy)
        deploy.state["github_setup_prompted"] = True
        deploy.save()
    if not deploy.state.get("skills_setup_prompted"):
        if ask_yes("Would you like to install AI skills?"):
            result = subprocess.run([sys.executable, str(ROOT / "scripts/skill_manager.py")])
            if result.returncode:
                print("Skill manager did not complete; rerun setup or skill-manager when ready.")
                return ["AI skills"]
        deploy.state["skills_setup_prompted"] = True
        deploy.save()
    return []


def main():
    if any(flag in sys.argv[1:] for flag in ("--help", "-h", "--preflight", "--dry-run", "--check")):
        return _main()
    with operation_lock():
        return _main()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print("\nSetup stopped. Rerun ./install.sh to continue.", file=sys.stderr)
        sys.exit(1)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f"linux-setup: {error}", file=sys.stderr)
        sys.exit(1)
