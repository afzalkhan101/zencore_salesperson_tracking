#!/usr/bin/env python3
"""Bump Odoo 19 module manifest versions for material Git changes.

Only repository-root Odoo modules are considered authoritative.  This keeps a
nested mobile application or copied addon reference directory from changing a
deployable module's version.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
DOC_SUFFIXES = {".adoc", ".md", ".mdx", ".rst", ".txt"}
DOC_DIRECTORIES = {"doc", "docs", "documentation"}
VERSION_LINE = re.compile(
    r"(?P<prefix>['\"]version['\"]\s*:\s*['\"])(?P<version>\d+(?:\.\d+)+)(?P<suffix>['\"])",
)


class UpgradeAutomationError(RuntimeError):
    """Raised when a revision or manifest cannot be handled safely."""


@dataclass(frozen=True)
class ChangedPath:
    status: str
    paths: tuple[str, ...]


@dataclass
class ModuleResult:
    name: str
    status: str
    reason: str
    old_version: str | None = None
    new_version: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "module": self.name,
            "status": self.status,
            "reason": self.reason,
            "old_version": self.old_version,
            "new_version": self.new_version,
        }


def git(repo: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    command = ["git", *args]
    completed = subprocess.run(
        command,
        cwd=repo,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        message = completed.stderr.decode("utf-8", "replace").strip()
        raise UpgradeAutomationError(f"Git command failed ({' '.join(command)}): {message}")
    return completed.stdout


def is_zero_sha(revision: str) -> bool:
    return bool(revision) and set(revision) == {"0"}


def resolve_revision(repo: Path, revision: str) -> str:
    if is_zero_sha(revision):
        return EMPTY_TREE
    return git(repo, "rev-parse", "--verify", f"{revision}^{{commit}}").decode().strip()


def root_modules_at_worktree(repo: Path) -> dict[str, Path]:
    """Return only top-level module directories from the checked-out revision."""
    modules: dict[str, Path] = {}
    for child in repo.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        if (child / "__manifest__.py").is_file():
            modules[child.name] = child
    return modules


def root_modules_at_revision(repo: Path, revision: str) -> set[str]:
    paths = git(repo, "ls-tree", "-r", "--name-only", revision).decode().splitlines()
    modules: set[str] = set()
    for path in paths:
        parts = path.split("/")
        if len(parts) == 2 and parts[1] == "__manifest__.py":
            modules.add(parts[0])
    return modules


def changed_paths(repo: Path, base: str, head: str) -> list[ChangedPath]:
    raw = git(repo, "diff", "--name-status", "-z", "--find-renames", base, head)
    tokens = raw.decode("utf-8", "surrogateescape").split("\0")
    if tokens and tokens[-1] == "":
        tokens.pop()
    changes: list[ChangedPath] = []
    index = 0
    while index < len(tokens):
        status = tokens[index]
        index += 1
        if not status:
            continue
        if status[0] in {"R", "C"}:
            if index + 1 >= len(tokens):
                raise UpgradeAutomationError("Malformed Git rename/copy diff output.")
            changes.append(ChangedPath(status, (tokens[index], tokens[index + 1])))
            index += 2
        else:
            if index >= len(tokens):
                raise UpgradeAutomationError("Malformed Git diff output.")
            changes.append(ChangedPath(status, (tokens[index],)))
            index += 1
    return changes


def module_for_path(path: str, module_names: set[str]) -> tuple[str, str] | None:
    parts = Path(path).parts
    if len(parts) < 2 or parts[0] not in module_names:
        return None
    return parts[0], Path(*parts[1:]).as_posix()


def is_documentation_path(relative_path: str) -> bool:
    path = Path(relative_path)
    lowered_parts = {part.lower() for part in path.parts[:-1]}
    return path.suffix.lower() in DOC_SUFFIXES or bool(lowered_parts & DOC_DIRECTORIES)


def file_at_revision(repo: Path, revision: str, path: str) -> str | None:
    completed = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        return None
    return completed.stdout.decode("utf-8", "surrogateescape")


def manifest_change_is_version_only(repo: Path, base: str, head: str, module: str) -> bool:
    path = f"{module}/__manifest__.py"
    before = file_at_revision(repo, base, path)
    after = file_at_revision(repo, head, path)
    if before is None or after is None:
        return False

    def without_version(value: str) -> str:
        return VERSION_LINE.sub(r"\g<prefix><VERSION>\g<suffix>", value, count=1)

    return without_version(before) == without_version(after)


def material_modules(
    repo: Path,
    base: str,
    head: str,
    changes: Iterable[ChangedPath],
    base_modules: set[str],
    head_modules: set[str],
) -> dict[str, list[str]]:
    all_modules = base_modules | head_modules
    material: dict[str, list[str]] = {}
    for change in changes:
        for path in change.paths:
            resolved = module_for_path(path, all_modules)
            if not resolved:
                continue
            module, relative_path = resolved
            if is_documentation_path(relative_path):
                continue
            if relative_path == "__manifest__.py" and manifest_change_is_version_only(repo, base, head, module):
                continue
            material.setdefault(module, []).append(path)
    return material


def parse_version(manifest: str, manifest_path: Path) -> tuple[re.Match[str], list[str]]:
    match = VERSION_LINE.search(manifest)
    if not match:
        raise UpgradeAutomationError(f"No numeric 'version' field found in {manifest_path}.")
    parts = match.group("version").split(".")
    if len(parts) < 3 or parts[:2] != ["19", "0"]:
        raise UpgradeAutomationError(
            f"{manifest_path} must use an Odoo 19 version beginning with '19.0.'; "
            f"found {match.group('version')!r}."
        )
    return match, parts


def bump_manifest(manifest_path: Path) -> tuple[str, str]:
    source = manifest_path.read_text(encoding="utf-8")
    match, parts = parse_version(source, manifest_path)
    old_version = match.group("version")
    parts[-1] = str(int(parts[-1]) + 1)
    new_version = ".".join(parts)
    updated = source[: match.start("version")] + new_version + source[match.end("version") :]
    manifest_path.write_text(updated, encoding="utf-8")
    return old_version, new_version


def process(repo: Path, base_arg: str, head_arg: str, write: bool) -> list[ModuleResult]:
    base = resolve_revision(repo, base_arg)
    head = resolve_revision(repo, head_arg)
    worktree_modules = root_modules_at_worktree(repo)
    base_modules = root_modules_at_revision(repo, base)
    head_modules = root_modules_at_revision(repo, head)
    changed = changed_paths(repo, base, head)
    material = material_modules(repo, base, head, changed, base_modules, head_modules)

    results: list[ModuleResult] = []
    for module in sorted(material):
        if module not in head_modules or module not in worktree_modules:
            results.append(ModuleResult(module, "skipped", "module removed; uninstalling is never automated"))
            continue
        if module not in base_modules:
            results.append(ModuleResult(module, "skipped", "new module; install it explicitly before later upgrades"))
            continue
        manifest_path = worktree_modules[module] / "__manifest__.py"
        source = manifest_path.read_text(encoding="utf-8")
        match, parts = parse_version(source, manifest_path)
        old_version = match.group("version")
        parts[-1] = str(int(parts[-1]) + 1)
        new_version = ".".join(parts)
        if write:
            old_version, new_version = bump_manifest(manifest_path)
        results.append(
            ModuleResult(
                module,
                "bumped" if write else "would-bump",
                "material module source, data, security, asset, or manifest change",
                old_version,
                new_version,
            )
        )

    if not results:
        results.append(ModuleResult("-", "skipped", "no material repository-root custom module changes"))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository root (default: current directory)")
    parser.add_argument("--base", required=True, help="Previous commit SHA (all-zero SHA is supported for a first push)")
    parser.add_argument("--head", default="HEAD", help="Current commit SHA (default: HEAD)")
    parser.add_argument("--write", action="store_true", help="Write bumped versions instead of producing a dry-run report")
    parser.add_argument("--json", action="store_true", help="Emit the result as JSON")
    args = parser.parse_args()

    try:
        repo = args.repo.resolve()
        results = process(repo, args.base, args.head, args.write)
    except (OSError, UpgradeAutomationError, ValueError) as error:
        print(f"odoo_auto_upgrade: {error}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps([result.as_dict() for result in results], indent=2))
    else:
        for result in results:
            version = ""
            if result.old_version and result.new_version:
                version = f" ({result.old_version} -> {result.new_version})"
            print(f"{result.status}: {result.name}{version} — {result.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
