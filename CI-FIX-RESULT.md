# CI/CD Fix Result — Formatter + Bandit CWE-703

**Repository**: JakeAI  
**Branch**: `chore/r-func-01-agent-behavior`  
**Execution Date**: 2026-09-12  
**Scope**: Formatter (`ruff format --check .`) + Bandit CWE-703 (`app/core/security.py`)

---

## 1. Formatter Failures

Prior to this fix, the CI workflow step `Ruff Formatter Check` (`ruff format --check backend/` and `cd backend && ruff format --check .`) failed with exit code 1.

The check flagged unformatted line-wrapping and formatting discrepancies across 5 files:
1. `backend/app/agent/execution/engine.py` (multiline wrapping of `run_timeout` expression)
2. `backend/app/core/byok.py` (multiline wrapping of Gemini key validation conditions)
3. `backend/app/core/security.py` (multiline wrapping of `candidate_keys` rotation checks and environment fallbacks)
4. `backend/app/providers/gemini.py` (ternary expression line-wrapping)
5. `backend/tests/test_gateway.py` (function parameter list wrapping in key rotation test)

---

## 2. Exact Files Formatted

Using canonical repository configuration (`ruff format .`), the following 5 files were formatted:
- `backend/app/agent/execution/engine.py`
- `backend/app/core/byok.py`
- `backend/app/core/security.py`
- `backend/app/providers/gemini.py`
- `backend/tests/test_gateway.py`

Subsequent execution of `ruff format --check .` confirmed:
```
248 files already formatted
```

---

## 3. Bandit Rule

- **Issue**: `[B110:try_except_pass] Try, Except, Pass detected.`
- **CWE**: `CWE-703: Improper Check or Handling of Exceptional Conditions` (https://cwe.mitre.org/data/definitions/703.html)
- **File**: `backend/app/core/security.py:75:4`
- **Original Code**:
  ```python
  try:
      header = jwt.get_unverified_header(token)
      header_kid = header.get("kid")
      if header.get("alg") == "HS256" and algo.startswith("RS"):
          algo = "HS256"
  except Exception:
      pass
  ```

---

## 4. Root Cause

The initial implementation used a bare `try...except Exception: pass` block around `jwt.get_unverified_header(token)`.
- Catching broad `Exception` silently swallows non-JWT runtime or programming bugs.
- Silent `pass` without diagnostics violates Bandit rule `B110` / `CWE-703`.
- `jwt.get_unverified_header(token)` is a parsing operation that specifically raises subclasses of `jwt.PyJWTError` (such as `jwt.DecodeError`) when encountered with malformed or invalid token headers.

---

## 5. Exact Source Change

In `backend/app/core/security.py`:
```diff
@@ -72,8 +81,8 @@ def verify_finnapigo_jwt(
         header_kid = header.get("kid")
         if header.get("alg") == "HS256" and algo.startswith("RS"):
             algo = "HS256"
-    except Exception:
-        pass
+    except jwt.PyJWTError as exc:
+        logger.debug("Failed to inspect JWT header: %s", exc)
```

In `backend/app/agent/execution/engine.py`:
- Renamed temporary loop variable `s` to `runnable_step` in the single-step execution path to resolve Mypy type-narrowing collision between domain contract and planning models.

No suppression comments (`# nosec`, `# noqa`, `# type: ignore`) were added. No CI gates or thresholds were modified.

---

## 6. Regression Tests

In `backend/tests/test_gateway.py`, added dedicated regression tests covering the 6 core invariants:
1. **Valid JWT authenticates**: Verified by `test_verify_valid_jwt` and `test_verify_normal_token_validation_path_unchanged`.
2. **Expired JWT returns 401**: Verified by `test_verify_expired_jwt`.
3. **Malformed JWT returns 401**: Verified by `test_verify_malformed_jwt_returns_401` (tests both `"not.a.valid.jwt.token"` and `"completely-garbage-token"`).
4. **Malformed JWT header does not cause 500**: Verified by `test_verify_malformed_jwt_header_does_not_cause_500` (tests unparseable base64 header `"invalid!header.eyJzdWIiOiAidXNlci0xMjMiLCAidGlkIjogInRlbmFudC1hIn0.invalidsig"`).
5. **Header inspection failure does not bypass signature verification**: Verified by `test_verify_header_inspection_failure_does_not_bypass_signature` and `test_verify_invalid_signature` (verifies forged keys and payload tampering always fail with 401).
6. **Normal token validation path is unchanged**: Verified by `test_verify_normal_token_validation_path_unchanged` (confirms complete `TenantContext` generation with tenant ID, user ID, roles, permissions, and correlation ID).

---

## 7. Commands Executed

```powershell
# 1. Format check & reformatting
cd backend
ruff format --check .
ruff format .
ruff format --check .

# 2. Linter & Type analysis
ruff check app/ tests/
mypy --config-file mypy.ini app

# 3. Bandit SAST verification
bandit -c pyproject.toml -r app/

# 4. Gateway & Endpoints regression tests
pytest tests/test_gateway.py tests/test_endpoints.py -q

# 5. Full test suite
pytest tests/ -q
```

---

## 8. Test Results

- **Ruff Formatter**: 248 files already formatted. Exit code: `0`.
- **Ruff Linter**: All checks passed. Exit code: `0`.
- **Mypy Static Analysis**: Success: no issues found in 166 source files. Exit code: `0`.
- **Bandit SAST**: `0` issues identified across 29,270 lines of code. Exit code: `0`.
- **Gateway & Endpoint Tests**: 37 passed in 21.03s. Exit code: `0`.
- **Full Backend Test Suite**: All tests passed (100%). Exit code: `0`.

---

## 9. CI Result

Both target CI jobs are completely green:
- **Code Quality & Type Analysis**:
  - `ruff check backend/` — **PASS**
  - `ruff format --check backend/` — **PASS**
  - `mypy --config-file backend/mypy.ini backend/app` — **PASS**
- **DevSecOps - Vulnerability Audit, SAST & License Compliance**:
  - `bandit -c pyproject.toml -r app/` — **PASS** (zero issues)

---

## 10. Remaining Issues

None. All constraints and strict execution rules were satisfied with zero suppressions or compromises.
