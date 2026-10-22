"""Every independent pip-audit job must cover the downstream FastEmbed identity."""

import shlex
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GUARD = ["python", "backend/vendor/verify_fastembed.py", "--check-installed"]


def audit_jobs():
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
        for name, job in workflow.get("jobs", {}).items():
            if any("pip-audit " in step.get("run", "") for step in job["steps"]):
                yield path.name, name, job["steps"]


def guard_commands(steps):
    for index, step in enumerate(steps):
        for line in step.get("run", "").splitlines():
            if shlex.split(line) == GUARD:
                yield index, step, shlex.split(line)


class SecurityWorkflowGuardTests(unittest.TestCase):
    def test_each_audit_job_requires_installed_guard_before_auditing(self):
        jobs = list(audit_jobs())
        self.assertTrue(jobs, "No dependency audit jobs discovered")
        self.assertTrue(
            {
                ("ci.yml", "static-and-quality"),
                ("nightly.yml", "nightly-security-and-static"),
            }.issubset({(workflow, job) for workflow, job, _ in jobs}),
            "Main and scheduled security jobs must retain pip-audit",
        )
        nightly = yaml.load(
            (ROOT / ".github/workflows/nightly.yml").read_text(), Loader=yaml.BaseLoader
        )
        self.assertTrue(
            nightly["on"]["schedule"], "Scheduled monitoring must remain enabled"
        )
        for workflow, job, steps in jobs:
            with self.subTest(workflow=workflow, job=job):
                guards = list(guard_commands(steps))
                self.assertTrue(
                    guards, "Audit job omits installed provenance/advisory guard"
                )
                index, step, _ = guards[0]
                self.assertNotIn("if", step, "Guard cannot be conditional")
                self.assertEqual(step.get("continue-on-error", "false"), "false")
                self.assertEqual(step["run"].strip(), " ".join(GUARD))
                install = next(
                    i
                    for i, s in enumerate(steps)
                    if "pip install -r backend/requirements.txt" in s.get("run", "")
                )
                audit = next(
                    i for i, s in enumerate(steps) if "pip-audit " in s.get("run", "")
                )
                self.assertLess(install, index)
                self.assertLess(index, audit)

    def test_actual_audit_workflow_commands_reject_active_upstream_advisory(self):
        # Execute the checked-in command in a fresh process. Only the external
        # PyPI response is replaced; argument parsing and rejection are real.
        harness = """
import io, json, runpy, sys, urllib.request
from unittest.mock import patch
document = {"info": {"name": "fastembed", "version": "0.8.0"},
            "vulnerabilities": [{"id": "GHSA-synthetic-workflow-regression"}]}
def response(url, **kwargs):
    assert url == "https://pypi.org/pypi/fastembed/0.8.0/json", url
    return io.BytesIO(json.dumps(document).encode())
sys.argv = sys.argv[1:]
with patch.object(urllib.request, "urlopen", response):
    runpy.run_path(sys.argv[0], run_name="__main__")
"""
        for workflow, job, steps in audit_jobs():
            with self.subTest(workflow=workflow, job=job):
                commands = list(guard_commands(steps))
                self.assertTrue(commands, "No workflow guard to exercise")
                result = subprocess.run(
                    [sys.executable, "-c", harness, *commands[0][2][1:]],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("GHSA-synthetic-workflow-regression", result.stderr)
                self.assertNotIn('"provenance": "PASS"', result.stdout)


if __name__ == "__main__":
    unittest.main()
