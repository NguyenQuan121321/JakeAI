"""Fail closed on every required GitHub Actions dependency result."""

import json
import os
import sys


def evaluate(needs: dict, required: list[str]) -> list[str]:
    """No required CI job is conditional; missing/skipped results are failures."""
    failures = []
    if not required or set(needs) != set(required):
        failures.append("Required job inventory does not match workflow dependencies")
    for name in required:
        result = needs.get(name, {}).get("result", "missing")
        print(f"{name}: {result}")
        if result != "success":
            failures.append(f"{name}: {result}")
    return failures


def main() -> int:
    failures = evaluate(json.loads(os.environ["NEEDS_JSON"]), os.environ["REQUIRED_JOBS"].split())
    if failures:
        print("CI / MERGE GATE: FAILED\n" + "\n".join(failures), file=sys.stderr)
        return 1
    print("CI / MERGE GATE: SUCCESS (all required jobs succeeded)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
