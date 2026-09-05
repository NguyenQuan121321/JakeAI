"""OpenAPI Breaking Change Detector & Contract Compatibility Checker.

Compares current OpenAPI specification against baseline git revision to detect:
1. Deleted endpoints or removed HTTP operations
2. Removed successful HTTP response status codes
3. New required request properties on existing endpoints
4. Altered data types or schema mutations
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# Ensure stdout/stderr handle UTF-8 cleanly on Windows/PowerShell
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def load_json_file(file_path: Path) -> dict[str, Any] | None:
    """Load JSON file from disk."""
    if not file_path.exists():
        return None
    try:
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"Error loading {file_path}: {exc}", file=sys.stderr)
        return None


def get_git_base_openapi(ref: str = "HEAD~1") -> dict[str, Any] | None:
    """Retrieve openapi.json from a previous git revision."""
    cmd = ["git", "show", f"{ref}:backend/openapi.json"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode == 0 and proc.stdout.strip():
            return json.loads(proc.stdout)
    except Exception:
        pass

    # Try root relative path
    cmd = ["git", "show", f"{ref}:openapi.json"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode == 0 and proc.stdout.strip():
            return json.loads(proc.stdout)
    except Exception:
        pass

    return None


def detect_breaking_changes(
    base: dict[str, Any], current: dict[str, Any]
) -> list[dict[str, str]]:
    """Compare two OpenAPI specs and return list of breaking changes."""
    breaking: list[dict[str, str]] = []

    base_paths = base.get("paths", {})
    curr_paths = current.get("paths", {})

    # 1. Check for removed paths
    for path in base_paths:
        if path not in curr_paths:
            breaking.append(
                {
                    "type": "REMOVED_ENDPOINT",
                    "location": path,
                    "detail": f"Path '{path}' was removed from the API.",
                }
            )

    # 2. Check for removed HTTP methods on existing paths
    for path, base_methods in base_paths.items():
        if path not in curr_paths:
            continue
        curr_methods = curr_paths[path]
        for method, base_op in base_methods.items():
            if method.lower() not in (
                "get",
                "post",
                "put",
                "delete",
                "patch",
                "options",
                "head",
            ):
                continue
            if method not in curr_methods:
                breaking.append(
                    {
                        "type": "REMOVED_METHOD",
                        "location": f"{method.upper()} {path}",
                        "detail": f"HTTP method '{method.upper()}' was removed from '{path}'.",
                    }
                )
                continue

            curr_op = curr_methods[method]

            # 3. Check for removed successful responses (200, 201, 204)
            base_responses = base_op.get("responses", {})
            curr_responses = curr_op.get("responses", {})
            for code in base_responses:
                if code.startswith("2") and code not in curr_responses:
                    breaking.append(
                        {
                            "type": "REMOVED_SUCCESS_RESPONSE",
                            "location": f"{method.upper()} {path} -> {code}",
                            "detail": f"Success response status '{code}' was removed.",
                        }
                    )

    # 4. Check for newly required properties in request bodies
    base_schemas = base.get("components", {}).get("schemas", {})
    curr_schemas = current.get("components", {}).get("schemas", {})

    for s_name, base_schema in base_schemas.items():
        if s_name not in curr_schemas:
            continue
        curr_schema = curr_schemas[s_name]

        base_required = set(base_schema.get("required", []))
        curr_required = set(curr_schema.get("required", []))
        newly_required = curr_required - base_required

        for prop in newly_required:
            breaking.append(
                {
                    "type": "NEW_REQUIRED_PROPERTY",
                    "location": f"#/components/schemas/{s_name}.{prop}",
                    "detail": f"Property '{prop}' in schema '{s_name}' is now strictly required.",
                }
            )

        # 5. Check for property type mutations
        base_props = base_schema.get("properties", {})
        curr_props = curr_schema.get("properties", {})
        for p_name, base_prop in base_props.items():
            if p_name in curr_props:
                b_type = base_prop.get("type")
                c_type = curr_props[p_name].get("type")
                if b_type and c_type and b_type != c_type:
                    breaking.append(
                        {
                            "type": "MUTATED_PROPERTY_TYPE",
                            "location": f"#/components/schemas/{s_name}.{p_name}",
                            "detail": f"Type mutated from '{b_type}' to '{c_type}'.",
                        }
                    )

    return breaking


def write_step_summary(summary_md: str) -> None:
    """Write markdown summary to GITHUB_STEP_SUMMARY."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(summary_md + "\n\n")
        except Exception as err:
            print(f"Failed to write GITHUB_STEP_SUMMARY: {err}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check OpenAPI breaking changes.")
    parser.add_argument(
        "--base-file", default=None, help="Path to base openapi.json file."
    )
    parser.add_argument(
        "--current-file",
        default="openapi.json",
        help="Path to current openapi.json file.",
    )
    parser.add_argument(
        "--git-ref",
        default="HEAD~1",
        help="Git revision to compare against (default: HEAD~1).",
    )
    args = parser.parse_args()

    curr_path = Path(args.current_file)
    if not curr_path.exists():
        curr_path = Path("backend") / args.current_file

    current_spec = load_json_file(curr_path)
    if not current_spec:
        print(f"❌ Current OpenAPI spec not found at '{curr_path}'.")
        sys.exit(1)

    base_spec: dict[str, Any] | None = None
    if args.base_file:
        base_spec = load_json_file(Path(args.base_file))
    else:
        base_spec = get_git_base_openapi(args.git_ref)

    if not base_spec:
        print(
            f"[INFO] No baseline OpenAPI spec found at revision '{args.git_ref}'. Skipping breaking change diff."
        )
        write_step_summary(
            "### [INFO] OpenAPI Contract Compatibility Check\n\n"
            f"> Baseline revision `{args.git_ref}` has no prior `openapi.json`. Comparison skipped for initial commit."
        )
        sys.exit(0)

    breaking_changes = detect_breaking_changes(base_spec, current_spec)

    if not breaking_changes:
        print(
            "================================================================================"
        )
        print("✅ OpenAPI Contract Compatibility Check PASSED.")
        print("Zero breaking changes detected against baseline revision.")
        print(
            "================================================================================"
        )
        write_step_summary(
            "### ✅ OpenAPI Contract Compatibility: **PASSED**\n\n"
            f"- Compared against: `{args.git_ref}`\n"
            "- **Status**: 100% Backward Compatible (Zero breaking changes detected)\n"
        )
        sys.exit(0)
    else:
        print(
            "================================================================================"
        )
        print(
            f"❌ BREAKING CHANGES DETECTED: {len(breaking_changes)} breaking mutation(s) found!"
        )
        print(
            "================================================================================"
        )
        for idx, bc in enumerate(breaking_changes, 1):
            print(f"{idx}. [{bc['type']}] {bc['location']}: {bc['detail']}")

        # Check for major release bypass indicator
        commit_msg = os.environ.get("COMMIT_MESSAGE", "")
        pr_title = os.environ.get("PR_TITLE", "")
        is_major_bump = (
            "!:" in commit_msg or "!:" in pr_title or "BREAKING CHANGE" in commit_msg
        )

        rows = "\n".join(
            [
                f"| `{b['type']}` | `{b['location']}` | {b['detail']} |"
                for b in breaking_changes
            ]
        )
        summary_md = (
            f"### ⚠️ OpenAPI Breaking Changes Detected ({len(breaking_changes)})\n\n"
            "| Issue Type | API Location | Description |\n"
            "| :--- | :--- | :--- |\n"
            f"{rows}\n\n"
        )

        if is_major_bump:
            print(
                "\n⚠️ Major release indicator detected in commit/PR. Allowing breaking changes."
            )
            summary_md += "> **Status**: Permitted via Conventional Commit Major Release (`BREAKING CHANGE` or `!:`).\n"
            write_step_summary(summary_md)
            sys.exit(0)
        else:
            summary_md += (
                "> ❌ **Status: FAILED**. Breaking changes are not permitted in minor/patch releases.\n"
                "> To allow breaking changes, include `!:` or `BREAKING CHANGE:` in the commit message or PR title."
            )
            write_step_summary(summary_md)
            sys.exit(1)


if __name__ == "__main__":
    main()
