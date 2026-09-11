# WORK-01-CI-FIX-05 — Execution Result: Secure & Centralize Structured Model Output Parsing

**Task**: WORK-01-CI-FIX-05  
**Capability**: 01 — AI Orchestration  
**Date**: September 12, 2026  
**Status**: RESOLVED  
**Branch**: `feat/work-01-ai-orchestration-final`  

---

## 1. Bandit / SAST Root Cause

GitHub Actions CI failed on the `dependency-and-sast` job at the Bandit step (`bandit -c pyproject.toml -r app/`):
- **CWE**: CWE-703 (Improper Check or Handling of Exceptional Conditions)
- **Rule**: `B110:try_except_pass` (Try, Except, Pass detected)
- **Findings Count**: Exactly 8 findings
- **Locations**:
  - `backend/app/agent/planning/planner.py`: lines 341, 349, 357, 365
  - `backend/app/agent/registry/agent_selector.py`: lines 310, 318, 326, 334

Both files contained identical local `_extract_json_dict()` static methods that used four repeated:
```python
try:
    ...
except Exception:
    pass
```
blocks around JSON parsing candidates.

---

## 2. Previous Duplicated Implementation

Both `planner.py` and `agent_selector.py` duplicated identical ~37-line static methods `_extract_json_dict(text: str) -> dict[str, Any] | None`:
- Attempted raw `{...}` parsing with broad `except Exception: pass`.
- Attempted ````json` codeblock parsing with broad `except Exception: pass`.
- Attempted generic ```` codeblock parsing with broad `except Exception: pass`.
- Attempted regex `r"\{.*\}"` greedy search with broad `except Exception: pass`.

This duplicated logic, swallowed unexpected runtime errors, and violated secure coding standards.

---

## 3. Canonical Utility Created

A centralized structured-output parsing module was created:
- **File**: `backend/app/agent/utils/structured_output.py`
- **Package Init**: `backend/app/agent/utils/__init__.py`
- **Function**: `extract_json_dict(text: str) -> dict[str, Any] | None`

### Extraction Sequence:
1. **Empty / Whitespace validation**: Returns `None` immediately.
2. **Raw JSON object parsing**: Validates top-level `{...}`. Also rejects top-level `[...]` arrays or primitive literals (`true`, `false`, `null`, numbers, strings) directly.
3. **Bounded ```json fenced code block extraction**: Locates opening ````json` and closing ````. Returns `None` if closing fence is missing (truncated/malformed output).
4. **Bounded generic ``` fenced code block extraction**: Locates opening ```` and closing ````, stripping optional language tags. Returns `None` if closing fence is missing.
5. **Bounded embedded JSON object extraction**:
   - First tests the outer `{ ... }` candidate.
   - Searches bounded regex `_BOUNDED_OBJECT_PATTERN = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}")` to handle braces inside surrounding prose.
   - Fallback balanced brace linear scan (strictly bounded, zero catastrophic backtracking risk).
6. **Return None**: For malformed or non-dictionary model outputs.

No arbitrary execution (`no eval`, `no exec`).

---

## 4. Exact Exception Policy

- Catches exclusively `json.JSONDecodeError` during JSON parsing attempts.
- **Zero** `except Exception:` blocks.
- **Zero** `except BaseException:` blocks.
- **Zero** `# noqa: B110` or `# nosec` suppressions.
- Any unexpected programming errors are raised normally rather than silently swallowed.

---

## 5. Planner Migration

In `backend/app/agent/planning/planner.py`:
- Deleted local duplicate `_extract_json_dict()` static method.
- Imported canonical `extract_json_dict` from `app.agent.utils.structured_output`.
- Updated call sites:
  - Initial plan generation: `parsed = extract_json_dict(resp.content)`
  - Plan retry generation: `retry_parsed = extract_json_dict(retry_resp.content)`
- Preserved existing schema validation (`_validate_dag_plan`) and deterministic DAG fallback policies (`create_initial_plan`).

---

## 6. Agent Selector Migration

In `backend/app/agent/registry/agent_selector.py`:
- Deleted local duplicate `_extract_json_dict()` static method.
- Removed unused `import json`.
- Imported canonical `extract_json_dict` from `app.agent.utils.structured_output`.
- Updated call site:
  - Model-assisted agent selection: `parsed = extract_json_dict(resp.content)`
- Preserved existing caller validation (`selected_agent_id` verification) and deterministic capability ranking / degraded mode fallbacks.

---

## 7. Tests & Verification Suite

Created `backend/tests/test_structured_output.py` covering 18 test cases:
1. `test_case_1_raw_json_object` — Raw JSON dictionary parsing.
2. `test_case_2_fenced_json_block` — ````json` fenced block extraction.
3. `test_case_3_generic_fenced_block` — Generic ```` fenced block extraction.
4. `test_case_4_embedded_json_object` — Embedded JSON object in surrounding prose.
5. `test_case_5_empty_text` — Empty text returns `None`.
6. `test_case_6_whitespace_only_text` — Whitespace-only text returns `None`.
7. `test_case_7_malformed_json` — Malformed JSON returns `None`.
8. `test_case_8_valid_json_array` — Valid JSON array returns `None`.
9. `test_case_9_valid_json_primitives` — String, integer, boolean primitives return `None`.
10. `test_case_10_missing_closing_fence` — Missing closing fence returns `None`.
11. `test_case_11_multiple_blocks` — Multiple blocks extracts first block deterministically.
12. `test_case_12_braces_inside_surrounding_prose` — Prose braces do not break extraction.
13. `test_case_13_malformed_embedded_object` — Malformed embedded object returns `None`.
14. `test_case_14_regression_no_broad_exceptions` — Inspects AST/source proving no `except Exception:` or suppressions exist.
15. `test_planner_integration_valid_structured_output` — Planner extracts structured DAG plan.
16. `test_planner_integration_none_fallback_deterministic` — Planner falls back to deterministic DAG when parser returns `None`.
17. `test_agent_selector_integration_valid_selection` — AgentSelector selects agent from structured model output.
18. `test_agent_selector_integration_none_fallback_deterministic` — AgentSelector falls back to deterministic selection when parser returns `None`.

All 18 tests passed (`0.29s`).

---

## 8. Quality Gate Verification Results

### Ruff Linter
```bash
$ uv run ruff check .
All checks passed!
Exit code: 0
```

### Ruff Formatter
```bash
$ uv run ruff format --check .
247 files already formatted
Exit code: 0
```

### Mypy Static Type Checking
```bash
$ uv run mypy --config-file mypy.ini app
Success: no issues found in 166 source files
Exit code: 0
```

### Bandit / SAST Security Scan
```bash
$ uv run bandit -c pyproject.toml -r app/
[main]	INFO	using config: pyproject.toml
Run metrics:
	Total issues (by severity):
		Undefined: 0
		Low: 0
		Medium: 0
		High: 0
Test results:
	No issues identified.
Exit code: 0
```

### WORK-01 Full Regression Suite
```bash
$ uv run pytest tests/test_structured_output.py \
                tests/test_orchestration_planner.py \
                tests/test_agent_registry_and_selector.py \
                tests/test_execution_engine_and_adapters.py \
                tests/test_architecture_invariants.py \
                tests/test_verifier_invariants.py \
                tests/test_orchestration_contracts.py
============================= 61 passed in 3.92s ==============================
Exit code: 0
```

---

## 9. Final Diff Summary

```
 backend/app/agent/planning/planner.py        | 44 ++--------------------------
 backend/app/agent/registry/agent_selector.py | 43 ++-------------------------
 backend/app/agent/utils/__init__.py          |  1 +
 backend/app/agent/utils/structured_output.py | 148 +++++++++++++++++++++++++++++
 backend/tests/test_structured_output.py      | 232 +++++++++++++++++++++++++++++
 5 files changed, 386 insertions(+), 82 deletions(-)
```

---

## 10. Remaining Issues

- **None**. Bandit CWE-703 / B110 issues are completely resolved with 0 findings.
- One canonical parser handles all structured model JSON extraction in JakeAI Orchestration.
