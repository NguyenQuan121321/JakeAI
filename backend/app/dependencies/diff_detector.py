"""Dependency diff detection between git revisions or requirements files (TEST-10)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from packaging.version import InvalidVersion, Version

from app.dependencies.manifest import (
    normalize_package_name,
    parse_requirements_file,
    resolve_category,
)
from app.dependencies.models import DependencyDiff


def parse_git_file_content(ref: str, file_path_in_repo: str) -> str | None:
    """Retrieve text content of a file from a specified git revision."""
    cmd = ["git", "show", f"{ref}:{file_path_in_repo}"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            return proc.stdout
    except Exception:
        pass
    return None


def parse_requirements_str(content: str) -> dict[str, str]:
    """Parse string formatted as requirements.txt into dict[normalized_name, version]."""
    reqs: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([a-zA-Z0-9_\-\[\]]+)\s*==\s*([a-zA-Z0-9\.\-]+)", line)
        if match:
            raw_pkg, version = match.groups()
            norm = normalize_package_name(raw_pkg)
            reqs[norm] = version
    return reqs


def compare_semver(old_ver_str: str, new_ver_str: str) -> tuple[bool, bool, str]:
    """Compare two version strings and determine major/minor bumps and diff type."""
    try:
        v_old = Version(old_ver_str)
        v_new = Version(new_ver_str)

        diff_type = (
            "upgrade"
            if v_new > v_old
            else ("downgrade" if v_new < v_old else "unchanged")
        )
        is_major = v_new.major != v_old.major
        is_minor = (v_new.major == v_old.major) and (v_new.minor != v_old.minor)
        return is_major, is_minor, diff_type
    except InvalidVersion:
        # Fallback heuristic
        diff_type = "upgrade" if new_ver_str != old_ver_str else "unchanged"
        parts_old = old_ver_str.split(".")
        parts_new = new_ver_str.split(".")
        is_major = parts_old[0] != parts_new[0] if parts_old and parts_new else False
        is_minor = (
            parts_old[:2] != parts_new[:2]
            if len(parts_old) >= 2 and len(parts_new) >= 2
            else False
        )
        return is_major, is_minor, diff_type


def detect_dependency_diffs(
    old_reqs: dict[str, str],
    new_reqs: dict[str, str],
) -> list[DependencyDiff]:
    """Compare two sets of requirements and return detected DependencyDiff records."""
    diffs: list[DependencyDiff] = []

    all_keys = sorted(set(old_reqs.keys()).union(new_reqs.keys()))

    for pkg in all_keys:
        old_ver = old_reqs.get(pkg)
        new_ver = new_reqs.get(pkg)

        if old_ver is None and new_ver is not None:
            # Newly added package
            diffs.append(
                DependencyDiff(
                    dependency=pkg,
                    category=resolve_category(pkg),
                    old_version="0.0.0",
                    new_version=new_ver,
                    diff_type="added",
                    is_major_bump=True,
                    is_minor_bump=False,
                )
            )
        elif old_ver is not None and new_ver is None:
            # Removed package
            diffs.append(
                DependencyDiff(
                    dependency=pkg,
                    category=resolve_category(pkg),
                    old_version=old_ver,
                    new_version="0.0.0",
                    diff_type="removed",
                    is_major_bump=True,
                    is_minor_bump=False,
                )
            )
        elif old_ver is not None and new_ver is not None and old_ver != new_ver:
            is_major, is_minor, diff_type = compare_semver(old_ver, new_ver)
            diffs.append(
                DependencyDiff(
                    dependency=pkg,
                    category=resolve_category(pkg),
                    old_version=old_ver,
                    new_version=new_ver,
                    diff_type=diff_type,
                    is_major_bump=is_major,
                    is_minor_bump=is_minor,
                )
            )

    return diffs


def detect_git_dependency_diffs(
    base_ref: str = "origin/main",
    backend_dir: Path | None = None,
) -> list[DependencyDiff]:
    """Compare requirements.txt against git base_ref to detect active PR dependency updates."""
    if backend_dir is None:
        backend_dir = Path(__file__).resolve().parent.parent.parent

    reqs_file = backend_dir / "requirements.txt"
    current_reqs = parse_requirements_file(reqs_file)

    # Attempt to load base_ref content from git
    base_content = parse_git_file_content(base_ref, "backend/requirements.txt")
    if base_content is None:
        # Fallback to HEAD~1 or local git rev-parse
        base_content = parse_git_file_content("HEAD~1", "backend/requirements.txt")

    if base_content is None:
        # No base found; compare against empty or return empty
        return []

    base_reqs = parse_requirements_str(base_content)
    return detect_dependency_diffs(base_reqs, current_reqs)
