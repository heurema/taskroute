"""Frozen local dependencies and explicit runtime capabilities for project checks."""

import hashlib
import json
import os
import re
import shutil
from pathlib import Path

FIELDS = {"dependency_roots", "executables", "loopback_ports", "cache_paths", "cache_environment"}


def relative(name):
    if not isinstance(name, str) or not name or "\0" in name or "\\" in name:
        raise ValueError("INVALID_DEPENDENCY_PATH")
    path = Path(name)
    if path.is_absolute() or str(path) != name or ".." in path.parts or not path.parts:
        raise ValueError("INVALID_DEPENDENCY_PATH")
    if any(part in {".git", "TASK.md", "checks.json"} for part in path.parts):
        raise ValueError("RESERVED_DEPENDENCY_PATH")
    return path


def beneath(name, parent):
    return Path(name) == Path(parent) or Path(parent) in Path(name).parents


def file_hash(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while data := stream.read(1048576):
            result.update(data)
    return result.hexdigest()


def tree_hash(root, ignored=()):
    """Bind binary/text bytes, executable modes and contained relative symlinks."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("DEPENDENCY_ROOT_UNAVAILABLE")
    result = hashlib.sha256()
    count = 0
    for directory, folders, files in os.walk(root, followlinks=False):
        base = Path(directory)
        folders[:] = sorted(
            name
            for name in folders
            if not any(beneath(str((base / name).relative_to(root)), skip) for skip in ignored)
        )
        for name in sorted([*folders, *files]):
            path = base / name
            rel = str(path.relative_to(root))
            if any(beneath(rel, skip) for skip in ignored):
                continue
            count += 1
            if count > 100000:
                raise ValueError("DEPENDENCY_TREE_TOO_LARGE")
            mode = path.lstat().st_mode & 0o777
            if path.is_symlink():
                target = os.readlink(path)
                if Path(target).is_absolute() or not path.resolve(strict=True).is_relative_to(
                    root.resolve()
                ):
                    raise ValueError("DEPENDENCY_SYMLINK_ESCAPE")
                row = [rel, "symlink", mode, target]
            elif path.is_file():
                row = [rel, "file", mode, file_hash(path)]
            elif path.is_dir():
                row = [rel, "directory", mode]
            else:
                raise ValueError("UNSUPPORTED_DEPENDENCY_ENTRY")
            result.update((json.dumps(row, separators=(",", ":")) + "\n").encode())
    return result.hexdigest()


def cache_paths(environment, name):
    return [str(Path(p).relative_to(name)) for p in environment["cache_paths"] if beneath(p, name)]


def validate(value, project, source_paths):
    if not isinstance(value, dict) or not set(value) <= FIELDS:
        raise ValueError("UNSUPPORTED_CHECK_ENVIRONMENT")
    if not value:
        return {}
    lists = {key: value.get(key, []) for key in FIELDS - {"cache_environment"}}
    for key, values in lists.items():
        if (
            not isinstance(values, list)
            or any(type(item) is not (int if key == "loopback_ports" else str) for item in values)
            or len(values) != len(set(values))
        ):
            raise ValueError("INVALID_CHECK_ENVIRONMENT")
    roots, caches, ports = (lists[k] for k in ("dependency_roots", "cache_paths", "loopback_ports"))
    if len(roots) > 8 or len(ports) > 4 or any(not 1024 <= p <= 65535 for p in ports):
        raise ValueError("INVALID_CHECK_ENVIRONMENT")
    for name in roots:
        path = relative(name)
        source = project / path
        if any(p.is_symlink() for p in [source, *source.parents]):
            raise ValueError("DEPENDENCY_ROOT_SYMLINK")
        if not source.resolve().is_relative_to(project):
            raise ValueError("DEPENDENCY_ROOT_ESCAPE")
        if any(beneath(p, name) or beneath(name, p) for p in source_paths):
            raise ValueError("DEPENDENCY_SOURCE_OVERLAP")
        if any(beneath(other, name) or beneath(name, other) for other in roots if other != name):
            raise ValueError("DEPENDENCY_ROOT_OVERLAP")
    for name in caches:
        relative(name)
        if not any(name != parent and beneath(name, parent) for parent in roots):
            raise ValueError("CACHE_OUTSIDE_DEPENDENCY_ROOT")
    tools = []
    for name in lists["executables"]:
        requested = Path(name)
        if not requested.is_absolute() or "\0" in name:
            raise ValueError("INVALID_RUNTIME_EXECUTABLE")
        binary = requested.resolve()
        if binary.is_relative_to(project) or not binary.is_file() or not os.access(binary, os.X_OK):
            raise ValueError("RUNTIME_EXECUTABLE_UNAVAILABLE")
        tools.append(dict(path=str(binary), sha256=file_hash(binary)))
    cache_env = value.get("cache_environment", {})
    if not isinstance(cache_env, dict):
        raise ValueError("INVALID_CACHE_ENVIRONMENT")
    for key, name in cache_env.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*_CACHE(?:_DIR)?", key):
            raise ValueError("INVALID_CACHE_ENVIRONMENT")
        relative(name)
        if any(beneath(name, p) or beneath(p, name) for p in source_paths + roots):
            raise ValueError("CACHE_ENVIRONMENT_OVERLAP")
    environment = dict(
        cache_paths=caches, loopback_ports=ports, executables=tools, cache_environment=cache_env
    )
    environment["dependency_roots"] = [
        dict(path=name, sha256=tree_hash(project / name, cache_paths(environment, name)))
        for name in roots
    ]
    return environment


def copy_tree(source, target, ignored):
    def ignore(directory, names):
        base = Path(directory)
        return [
            name
            for name in names
            if any(beneath(str((base / name).relative_to(source)), skip) for skip in ignored)
        ]

    shutil.copytree(source, target, symlinks=True, ignore=ignore)


def prepare(root, manifest):
    environment = manifest.get("check_environment") or {}
    for entry in environment.get("dependency_roots", []):
        name = entry["path"]
        source = Path(manifest["project_root"]) / name
        target = Path(root) / "dependencies" / name
        ignored = cache_paths(environment, name)
        copy_tree(source, target, ignored)
        if (
            tree_hash(target, ignored) != entry["sha256"]
            or tree_hash(source, ignored) != entry["sha256"]
        ):
            raise ValueError("DEPENDENCY_CHANGED_DURING_PREPARATION")


def verify(manifest):
    environment = manifest.get("check_environment") or {}
    if not isinstance(environment, dict) or (environment and set(environment) != FIELDS):
        raise ValueError("UNSUPPORTED_CHECK_ENVIRONMENT")
    if not environment:
        return
    root = Path(manifest["workspace"]).parent
    for tool in environment.get("executables", []):
        binary = Path(tool["path"])
        if not os.access(binary, os.X_OK) or file_hash(binary) != tool["sha256"]:
            raise ValueError("RUNTIME_EXECUTABLE_CHANGED")
    for entry in environment.get("dependency_roots", []):
        name = entry["path"]
        ignored = cache_paths(environment, name)
        for directory in [Path(manifest["project_root"]) / name, root / "dependencies" / name]:
            if tree_hash(directory, ignored) != entry["sha256"]:
                raise ValueError("FROZEN_DEPENDENCY_CHANGED")


def install_copy(root, manifest, destination):
    environment = manifest.get("check_environment") or {}
    for entry in environment.get("dependency_roots", []):
        name = entry["path"]
        copy_tree(
            Path(root) / "dependencies" / name, destination / name, cache_paths(environment, name)
        )


def verify_copy(manifest, directory):
    environment = manifest.get("check_environment") or {}
    for entry in environment.get("dependency_roots", []):
        if (
            tree_hash(directory / entry["path"], cache_paths(environment, entry["path"]))
            != entry["sha256"]
        ):
            raise ValueError("CHECK_DEPENDENCY_MUTATED")


def policy_options(manifest):
    environment = manifest.get("check_environment") or {}
    return dict(
        loopback_ports=environment.get("loopback_ports", []),
        read_files=[t["path"] for t in environment.get("executables", [])],
    )


def executable_paths(manifest):
    return list(
        dict.fromkeys(
            str(Path(t["path"]).parent)
            for t in (manifest.get("check_environment") or {}).get("executables", [])
        )
    )


def environment_values(manifest, directory):
    return {
        key: str(directory / name)
        for key, name in (manifest.get("check_environment") or {})
        .get("cache_environment", {})
        .items()
    }
