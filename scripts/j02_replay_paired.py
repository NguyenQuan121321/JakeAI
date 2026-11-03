"""Diagnostic replay of the immutable five pairs, never a qualified CI PASS."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.performance.paired import (
    CONTROL_SHA,
    FULL,
    phase_findings,
    sample_errors,
)

COHORT_SHA256 = "3dd3f56b3ae9c9f3cea0fa39a63b02b2b50dcaf531dd943b30385ec3207cd61b"


def replay(path):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != COHORT_SHA256:
        raise ValueError("Exact immutable cohort required")
    data = json.loads(raw)
    pairs = sorted(
        (r["data"] for r in data["receipts"] if r["tag"] == "J02_CALIBRATION_PAIR"),
        key=lambda r: r["pair"],
    )
    if [pair["pair"] for pair in pairs] != [1, 2, 3, 4, 5]:
        raise ValueError("All five prescribed pairs required")
    results, operations = [], 0
    for pair in pairs:
        subjects = pair["subjects"]
        initial = {
            "candidate": subjects["candidate"]["results"]["report"][
                "initial_scenarios"
            ],
            "control": subjects["control"]["initial_scenarios"],
        }
        confirmation = {
            role: subjects[role]["results"]["scenarios"]
            for role in ("candidate", "control")
        }
        record = {
            "pair": pair["pair"],
            "original_control_sha": subjects["control"]["actual_source"],
            "required_control_sha": CONTROL_SHA,
            "initial": initial,
            "confirmation": confirmation,
            "numeric_findings": {},
            "integrity_findings": {},
            "qualified_verdict": "INCONCLUSIVE_BLOCKED",
            "exit_code": 2,
        }
        for phase, samples in (("initial", initial), ("confirmation", confirmation)):
            record["numeric_findings"][phase] = phase_findings(
                samples["candidate"], samples["control"]
            )
            record["integrity_findings"][phase] = {
                role: sample_errors(values, set(FULL))
                for role, values in samples.items()
            }
            operations += sum(
                value["total_requests"]
                for role in samples.values()
                for value in role.values()
            )
        results.append(record)
    if operations != 3420:
        raise ValueError("Original workload denominator changed")
    return {
        "scope": "FROZEN_DIAGNOSTIC_ONLY_NO_NEW_LOAD",
        "operations_retained": operations,
        "scenario_records_retained": 240,
        "qualification_gaps": [
            "Original control bed2473 is post-J02, not pinned pre-J02 64f087c",
            "Live configuration/CPU/quotas were not captured",
            "Harness/usefulness checks differ; no fresh hosted paired execution",
        ],
        "pairs": results,
        "exit_code": 2,
        "verdict": "INCONCLUSIVE_BLOCKED",
    }


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(arguments)
    result = replay(args.frozen)
    args.output.write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
