"""Opt-in paired CI comparison. No legacy selector, baseline or gate changes.

Exit 0: equivalent within tolerances; 1: candidate regression/fatal sample;
2: inconclusive evidence/control. Both nonzero outcomes block activation.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.performance.baseline_store import PerformanceBaselineStore
from app.performance.contracts import ScenarioResult
from app.performance.regression_detector import (
    PerformanceRegressionDetector as Detector,
)

CONTROL_SHA = "64f087ca708200a2c81ba646acfa6112876f601c"
FULL = {
    "concurrent_chat": (30, 10),
    "concurrent_agent_runs": (15, 5),
    "concurrent_rag_queries": (30, 10),
    "sse_connections": (16, 8),
    "redis_contention": (50, 15),
    "qdrant_access": (30, 10),
}
WORKLOAD = "full-1.0-three-tenants-all-miss-search-plus-upsert-v1"
REDIS_IMAGE = "sha256:8da19c7399dca900c6822a1cf30f9d2285585e2c4b457ff4095b0f4500054d3f"
QDRANT_IMAGE = "sha256:d774e7bb65744454984c6021637a0da89271f30df15e48601a9fafc926d26b1f"
# Reuse the existing old-main subprocess capture bound, not a production SLO.
CAPTURE_SECONDS = 180
ROLES = ("control", "candidate")


def validate_subjects(subjects: dict) -> None:
    if set(subjects) != set(ROLES):
        raise ValueError("Both independently measured subjects are required")
    candidate, control = subjects["candidate"], subjects["control"]
    if control["source_sha"] != CONTROL_SHA or candidate["source_sha"] == CONTROL_SHA:
        raise ValueError("Pinned pre-J02 control must differ from candidate")
    for subject in subjects.values():
        if not all(
            re.fullmatch("[0-9a-f]{40}", subject[key])
            for key in ("source_sha", "source_tree")
        ):
            raise ValueError("Source identity missing")
        context = subject["context"]
        if set(context) != {
            "job",
            "runtime",
            "dependencies",
            "harness_sha256",
            "stores",
            "workload",
        }:
            raise ValueError("Context schema mismatch")
        if context["workload"] != WORKLOAD or not re.fullmatch(
            "[0-9a-f]{64}", context["harness_sha256"]
        ):
            raise ValueError("Harness/workload mismatch")
        if set(context["job"]) != {"run", "attempt", "job"} or not all(
            context["job"].values()
        ):
            raise ValueError("Job identity missing")
        runtime = context["runtime"]
        if (
            set(runtime) != {"python", "runner", "image", "os", "cpu", "quota", "cores"}
            or runtime["python"] != "3.12.15"
            or runtime["runner"] != "ubuntu-24.04"
            or runtime["os"] != "Linux"
            or not all(runtime.values())
            or runtime["cpu"] == "unknown"
            or runtime["quota"] == "unknown"
        ):
            raise ValueError("Runtime identity missing/incompatible")
        if not context["dependencies"] or not all(
            isinstance(k, str) and isinstance(v, str) and v
            for k, v in context["dependencies"].items()
        ):
            raise ValueError("Installed dependency inventory required")
        stores = context["stores"]
        if set(stores) != {"redis", "qdrant"}:
            raise ValueError("Both real stores required")
        redis, qdrant = stores["redis"], stores["qdrant"]
        if (
            redis["image"] != REDIS_IMAGE
            or redis["version"] != "7.4.12"
            or redis["configuration"]
            != {
                "appendonly": "no",
                "appendfsync": "everysec",
                "maxmemory-policy": "noeviction",
                "maxmemory": "0",
            }
            or qdrant["image"] != QDRANT_IMAGE
            or qdrant["version"] != "1.12.1"
        ):
            raise ValueError("Real store image/configuration mismatch")
        config = qdrant["configuration"]
        service = config["service"]
        if (
            service["http_port"] != 6333
            or service.get("enable_tls", False)
            or service.get("api_key")
            or service.get("read_only_api_key")
            or not config["storage"]["storage_path"]
            or not qdrant["configuration_sources"]
        ):
            raise ValueError("Effective Qdrant configuration missing/incompatible")
        if set(subject["instances"]) != {"redis", "qdrant"} or not all(
            subject["instances"].values()
        ):
            raise ValueError("Isolated service identities missing")
    if candidate["context"] != control["context"]:
        raise ValueError("Subjects differ in job/dependencies/stores/harness/workload")
    if set(candidate["instances"].values()) & set(control["instances"].values()):
        raise ValueError("Subject stores must remain isolated across phases")


def _finite(value: Any) -> bool:
    if isinstance(value, dict):
        return all(_finite(v) for v in value.values())
    if isinstance(value, list):
        return all(_finite(v) for v in value)
    return not isinstance(value, float) or math.isfinite(value)


def sample_errors(samples: dict, expected: set[str]) -> dict[str, str]:
    errors = dict.fromkeys(
        set(samples) ^ expected, "Missing/extra scenario measurement"
    )
    for name, raw in samples.items():
        try:
            sample = ScenarioResult.model_validate(raw)
            count, concurrency = FULL[name]
            latency, throughput = sample.latency.overall_ms, sample.throughput
            if (
                not _finite(raw)
                or sample.scenario_name != name
                or sample.total_requests != count
                or sample.success_count != count
                or sample.error_count != 0
                or sample.error_rate_pct != 0
                or sample.concurrency != concurrency
                or throughput.concurrency_level != concurrency
                or throughput.total_requests != count
                or latency.count != count
                or not 0 < latency.median_p50 <= latency.p95 <= latency.p99
                or throughput.requests_per_second <= 0
                or throughput.duration_seconds <= 0
                or throughput.duration_seconds > CAPTURE_SECONDS
                or abs(
                    throughput.requests_per_second - count / throughput.duration_seconds
                )
                > 0.01 + throughput.requests_per_second * 0.001
                or sample.custom_metrics.get("integrity_errors")
            ):
                raise ValueError("Invalid/incomplete/error/slow measurement")
            if name == "sse_connections" and (
                sample.latency.ttfc_ms.count != count or sample.latency.ttfc_ms.p95 <= 0
            ):
                raise ValueError("Streaming TTFC measurement missing")
            flag = {
                "redis_contention": "is_live_redis",
                "qdrant_access": "is_live_qdrant",
            }.get(name)
            if flag and sample.custom_metrics.get(flag) is not True:
                raise ValueError("Required real store unavailable/fallback")
            if name == "redis_contention" and (
                sample.cache is None or sample.cache.tier1_exact_hits != 0
            ):
                raise ValueError("Changed cache workload")
        except (KeyError, TypeError, ValueError, ValidationError):
            errors[name] = (
                "Fatal request/correctness/security/store/measurement integrity"
            )
    if (
        sum(
            raw.get("throughput", {}).get("duration_seconds", 0)
            for raw in samples.values()
        )
        > CAPTURE_SECONDS
    ):
        errors.update(
            dict.fromkeys(expected, "Unusable phase exceeds existing capture deadline")
        )
    return errors


def phase_findings(candidate: dict, control: dict) -> list[dict]:
    baseline = PerformanceBaselineStore().load_baseline("v1")
    findings = []
    for name in sorted(set(candidate) & set(control) & set(FULL)):
        try:
            current, reference = (
                ScenarioResult.model_validate(candidate[name]),
                ScenarioResult.model_validate(control[name]),
            )
            tolerance = baseline.scenarios[name].tolerances
            for metric, observed, ref in (
                (
                    "latency_p50_ms",
                    current.latency.overall_ms.median_p50,
                    reference.latency.overall_ms.median_p50,
                ),
                (
                    "latency_p95_ms",
                    current.latency.overall_ms.p95,
                    reference.latency.overall_ms.p95,
                ),
                (
                    "latency_p99_ms",
                    current.latency.overall_ms.p99,
                    reference.latency.overall_ms.p99,
                ),
                *(
                    (
                        [
                            (
                                "ttfc_p95_ms",
                                current.latency.ttfc_ms.p95,
                                reference.latency.ttfc_ms.p95,
                            )
                        ]
                    )
                    if name == "sse_connections"
                    else []
                ),
            ):
                if ref <= 0 or not math.isfinite(ref):
                    continue
                finding = Detector.evaluate_metric(
                    name,
                    metric,
                    ref,
                    observed,
                    tolerance["allowed_latency_regression_pct"],
                    tolerance["min_significant_delta_ms"],
                )
                findings.append(finding.model_dump(mode="json"))
            ref, observed = (
                reference.throughput.requests_per_second,
                current.throughput.requests_per_second,
            )
            fraction = tolerance["allowed_throughput_regression_pct"] / 100
            # Unrounded ratio and adaptive floor avoid the old low-reference
            # dead zone. At high references the original 25-rps filter remains.
            floor = min(
                tolerance.get(
                    "min_significant_delta_rps",
                    Detector.DEFAULT_MIN_SIGNIFICANT_DELTA_RPS,
                ),
                ref * fraction,
            )
            fails = observed < ref * (1 - fraction) and ref - observed >= floor
            findings.append(
                {
                    "scenario": name,
                    "metric_name": "throughput_rps",
                    "baseline_value": ref,
                    "current_value": observed,
                    "threshold": ref * (1 - fraction),
                    "absolute_drop_floor": floor,
                    "verdict": "FAIL" if fails else "PASS",
                }
            )
        except (KeyError, TypeError, ValueError, ValidationError):
            # Explicit fatal integrity findings below own the failed sample.
            continue
    return findings


def compare(evidence: dict, *, require_confirmation: bool = True) -> dict:
    """Pure audit, retaining all observations. Never manufactures a control."""
    report: dict[str, Any] = {
        "contract": "paired-ci-review-v1",
        "active_contract_changed": False,
        "evidence": copy.deepcopy(evidence),
        "initial_findings": [],
        "confirmation_findings": [],
        "fatal_errors": {},
        "confirmation_required": [],
        "exit_code": 2,
        "verdict": "INCONCLUSIVE_BLOCKED",
    }
    try:
        validate_subjects(evidence["subjects"])
        initial, confirmation = evidence["initial"], evidence["confirmation"]
        if set(initial) != set(ROLES) or set(confirmation) != set(ROLES):
            raise ValueError("Both subject phases must be recorded")
        if set(confirmation["control"]) != set(confirmation["candidate"]):
            raise ValueError("Unmatched confirmation measurements")
        fatal = {}
        for role in ROLES:
            fatal[role] = {"initial": sample_errors(initial[role], set(FULL))}
        findings = phase_findings(initial["candidate"], initial["control"])
        names = {f["scenario"] for f in findings if f["verdict"] == "FAIL"}
        names |= set(fatal["candidate"]["initial"]) | set(fatal["control"]["initial"])
        report["initial_findings"] = findings
        report["confirmation_required"] = sorted(names & set(FULL))
        for role in ROLES:
            fatal[role]["confirmation"] = sample_errors(
                confirmation[role], set(confirmation[role])
            )
        report["confirmation_findings"] = phase_findings(
            confirmation["candidate"], confirmation["control"]
        )
        for finding in findings:
            finding["is_reproducible"] = (
                any(
                    other["scenario"] == finding["scenario"]
                    and other["metric_name"] == finding["metric_name"]
                    and other["verdict"] == "FAIL"
                    for other in report["confirmation_findings"]
                )
                if finding["verdict"] == "FAIL"
                else True
            )
        report["fatal_errors"] = fatal
        if any(fatal["control"].values()):
            report["reason"] = "Invalid/unusably slow control; comparison cannot pass"
            return report
        if any(fatal["candidate"].values()):
            report.update(
                exit_code=1,
                verdict="FAIL",
                reason="Fatal candidate errors remain blocking across phases",
            )
            return report
        if require_confirmation and any(
            not names <= set(confirmation[role]) for role in ROLES
        ):
            report["reason"] = "Missing matched fixed confirmation"
            return report
        if names and not require_confirmation:
            report["reason"] = "Matched confirmation required before a timing verdict"
            return report
        final = [f for f in report["confirmation_findings"] if f["scenario"] in names]
        failed = any(f["verdict"] == "FAIL" for f in final)
        report.update(
            exit_code=int(failed),
            verdict="FAIL" if failed else "PASS",
            reason="One matched confirmation decides timing; fatal errors never recover",
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        AttributeError,
        OverflowError,
        ValidationError,
    ) as error:
        report["reason"] = "Missing/incompatible evidence: " + type(error).__name__
    return report


class PairedComparisonRunner:
    """Measure both subjects, then at most one matched confirmation per failure."""

    def __init__(self, subjects: dict, measure: Any) -> None:
        self.subjects, self.measure = subjects, measure

    async def run(self) -> dict:
        evidence: dict[str, Any] = {
            "subjects": copy.deepcopy(self.subjects),
            "initial": {role: {} for role in ROLES},
            "confirmation": {role: {} for role in ROLES},
        }
        try:
            validate_subjects(self.subjects)
            for role in ROLES:
                evidence["initial"][role] = await self.measure(
                    role, "initial", sorted(FULL)
                )
            first = compare(evidence, require_confirmation=False)
            names = first["confirmation_required"]
            if names:
                for role in ROLES:
                    evidence["confirmation"][role] = await self.measure(
                        role, "confirmation", names
                    )
            return compare(evidence)
        except Exception as error:
            # Never echo exception text containing subprocess credentials.
            return {
                "exit_code": 2,
                "verdict": "INCONCLUSIVE_BLOCKED",
                "reason": "Capture failure: " + type(error).__name__,
                "evidence": evidence,
            }


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inactive paired CI evidence audit; never clears legacy v1"
    )
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(arguments)
    try:

        def reject_constant(_value: str) -> None:
            raise ValueError("Non-finite JSON measurement")

        report = compare(
            json.loads(
                args.evidence.read_text(encoding="utf-8"),
                parse_constant=reject_constant,
            )
        )
    except (OSError, ValueError):
        report = {
            "exit_code": 2,
            "verdict": "INCONCLUSIVE_BLOCKED",
            "reason": "Missing/malformed evidence file",
        }
    args.output.write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
