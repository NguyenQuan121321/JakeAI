"""Exercise the same entry point as the aggregate CI job."""

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

import yaml


class MergeGateTests(unittest.TestCase):
    def test_workflow_inventory_and_always_condition(self):
        jobs = yaml.safe_load(
            (Path(__file__).parents[2] / ".github/workflows/ci.yml").read_text()
        )["jobs"]
        gate = jobs["merge-gate"]
        self.assertEqual(gate["if"], "${{ always() }}")
        self.assertEqual(set(gate["needs"]), set(jobs) - {"merge-gate"})
        self.assertEqual(
            set(next(step for step in gate["steps"] if "env" in step)["env"]["REQUIRED_JOBS"].split()), set(gate["needs"])
        )

    def run_gate(self, needs: dict, required: str = "security container") -> int:
        return subprocess.run(
            [sys.executable, str(Path(__file__).parents[1] / "check_merge_gate.py")],
            env={**os.environ, "NEEDS_JSON": json.dumps(needs), "REQUIRED_JOBS": required},
            capture_output=True,
            check=False,
        ).returncode

    def test_success(self):
        self.assertEqual(self.run_gate({name: {"result": "success"} for name in ["security", "container"]}), 0)

    def test_required_non_success(self):
        for result in ["failure", "cancelled", "skipped", "unknown"]:
            with self.subTest(result=result):
                self.assertEqual(self.run_gate({"security": {"result": result}, "container": {"result": "success"}}), 1)

    def test_missing_and_unexpected_jobs(self):
        self.assertEqual(self.run_gate({"security": {"result": "success"}}), 1)
        self.assertEqual(self.run_gate({"security": {"result": "success"}, "container": {"result": "success"}, "extra": {"result": "success"}}), 1)
        self.assertEqual(self.run_gate({}, ""), 1)


if __name__ == "__main__":
    unittest.main()
