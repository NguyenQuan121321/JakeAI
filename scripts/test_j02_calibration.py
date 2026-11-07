"""No stores/providers: verify fixed allocation, honest gates and retained failures."""

import copy
import unittest

from j02_benchmark_control import FULL
from j02_calibrate_performance import LANES, ORDERS, candidate_outcome, measure_pairs


def payload():
    results = {}
    for name, (count, concurrency) in FULL.items():
        results[name] = {"scenario_name": name, "total_requests": count,
            "success_count": count, "error_count": 0, "error_rate_pct": 0,
            "concurrency": concurrency, "latency": {"overall_ms": {"count": count}},
            "throughput": {"total_requests": count, "concurrency_level": concurrency},
            "custom_metrics": {"is_live_redis": True, "is_live_qdrant": True}}
    return {"report": {"initial_scenarios": copy.deepcopy(results),
            "has_blocking_regressions": True, "verdict": "FAIL"}, "scenarios": results}


class CalibrationTests(unittest.TestCase):
    def test_fixed_cohort_has_five_pairs_across_two_runners(self):
        self.assertEqual([pair for lane in LANES.values() for pair in lane], [1, 2, 3, 4, 5])
        for pairs in LANES.values():
            self.assertEqual({ORDERS[pair] for pair in pairs}, {("candidate", "control"), ("control", "candidate")})

    def test_candidate_threshold_failure_remains_a_failed_gate(self):
        result = candidate_outcome(1, payload())
        self.assertTrue(result["gate_failed"])
        self.assertEqual(result["performance_verdict"], "FAIL")

    def test_invalid_exit_and_requests_are_not_measurement_success(self):
        with self.assertRaises(ValueError):
            candidate_outcome(2, payload())
        with self.assertRaises(ValueError):
            candidate_outcome(0, payload())
        data = payload()
        data["report"]["initial_scenarios"]["concurrent_chat"]["error_count"] = 1
        with self.assertRaises(ValueError):
            candidate_outcome(1, data)

    def test_within_thresholds_is_valid_without_forgiving_a_failure(self):
        data = payload()
        data["report"].update(has_blocking_regressions=False, verdict="WARN")
        result = candidate_outcome(0, data)
        self.assertFalse(result["gate_failed"])
        self.assertEqual(measure_pairs("B", lambda pair: result, lambda pair: {}, lambda tag, data: None), 0)

    def test_every_pair_retained_after_candidate_and_integrity_failures(self):
        for lane in LANES:
            calls, receipts = [], []
            def candidate(pair):
                calls.append((pair, "candidate"))
                return {"gate_failed": True, "performance_verdict": "FAIL"}
            def control(pair):
                calls.append((pair, "control"))
                if pair == LANES[lane][0]:
                    raise ValueError("invalid capture")
                return {"diagnostic_outcome": {"classification": "DIAGNOSTIC_THRESHOLD_FAILURE"}}
            code = measure_pairs(lane, candidate, control, lambda tag, data: receipts.append(data))
            self.assertEqual(code, 1)
            self.assertEqual(calls, [(pair, role) for pair in LANES[lane] for role in ORDERS[pair]])
            self.assertEqual([r["pair"] for r in receipts], list(LANES[lane]))
            self.assertEqual(receipts[0]["subjects"]["control"]["integrity"], "INVALID")


if __name__ == "__main__":
    unittest.main()
