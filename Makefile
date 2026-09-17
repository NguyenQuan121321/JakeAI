.PHONY: help install dev lint format typecheck test test-cov eval audit sast openapi docker-up docker-down clean bruno-smoke bruno-e2e bruno-full bruno-live dep-audit dep-diff dep-validate ci-pr ci-main ci-report flaky-check

PYTHON ?= python
UV ?= uv
UVICORN ?= uvicorn
PYTEST ?= pytest
RUFF ?= ruff
MYPY ?= mypy
BANDIT ?= bandit
PIP_AUDIT ?= pip-audit

help:
	@echo "JakeAI Platform Management Commands:"
	@echo "  make install      Install backend production and development dependencies"
	@echo "  make dev          Start local FastAPI development server with hot reload"
	@echo "  make lint         Run Ruff lint checks"
	@echo "  make format       Format code with Ruff"
	@echo "  make typecheck    Run static type analysis with Mypy"
	@echo "  make test         Execute pytest test suite"
	@echo "  make test-cov     Execute pytest with coverage report"
	@echo "  make eval         Run AI RAG regression tests against golden dataset"
	@echo "  make bruno-smoke  Run Bruno CLI smoke test suite"
	@echo "  make bruno-e2e    Run Bruno CLI critical-e2e test suite"
	@echo "  make bruno-full   Run complete Bruno CLI test suite"
	@echo "  make bruno-live   Run Bruno CLI live integration suite"
	@echo "  make perf-smoke   Run fast performance regression smoke suite (<10s)"
	@echo "  make perf-full    Run full statistical performance load benchmark"
	@echo "  make perf-baseline Record new versioned empirical baseline"
	@echo "  make dep-audit    Audit all dependencies across 11 architectural categories"
	@echo "  make dep-diff     Detect dependency version deltas against base reference"
	@echo "  make dep-validate Execute automated dependency regression validation suites"
	@echo "  make ci-pr        Execute local PR Gate verification suite"
	@echo "  make ci-main      Execute local Main Gate verification suite"
	@echo "  make ci-report    Consolidate test failure and forensic reporting"
	@echo "  make flaky-check  Scan test suite for intermittent / flaky test behavior"
	@echo "  make audit        Scan dependencies for CVEs using pip-audit"
	@echo "  make sast         Run static application security testing using Bandit"
	@echo "  make openapi      Export static OpenAPI specification JSON"
	@echo "  make docker-up    Start backend, Redis, and Qdrant via Docker Compose"
	@echo "  make docker-down  Stop all running Docker Compose services"
	@echo "  make clean        Remove cache files, build artifacts, and coverage data"

install:
	cd backend && $(UV) pip install -r requirements.txt

dev:
	cd backend && $(UVICORN) app.main:app --host 0.0.0.0 --port 8000 --reload

lint:
	cd backend && $(RUFF) check .

format:
	cd backend && $(RUFF) format .

typecheck:
	cd backend && $(MYPY) app

test:
	cd backend && $(PYTEST) tests/ -v

test-cov:
	cd backend && $(PYTEST) --cov=app tests/ -v --cov-report=term-missing --cov-report=html

eval:
	cd backend && $(PYTEST) tests/evals/ -v

bruno-smoke:
	$(PYTHON) scripts/run_bruno_tests.py --suite smoke

bruno-e2e:
	$(PYTHON) scripts/run_bruno_tests.py --suite critical-e2e

bruno-full:
	$(PYTHON) scripts/run_bruno_tests.py --suite full

bruno-live:
	$(PYTHON) scripts/run_bruno_tests.py --suite live-release

perf-smoke:
	cd backend && $(PYTHON) scripts/run_performance_benchmark.py --mode smoke --fail-on-regression
	cd backend && $(PYTEST) tests/performance/test_performance_smoke.py tests/performance/test_performance_regression_gate.py -v

perf-full:
	cd backend && $(PYTHON) scripts/run_performance_benchmark.py --mode full --fail-on-regression
	cd backend && $(PYTEST) tests/performance/test_load_and_concurrency.py -v

perf-baseline:
	cd backend && $(PYTHON) scripts/run_performance_benchmark.py --mode baseline-record --baseline-version v1

dep-audit:
	cd backend && $(PYTHON) scripts/run_dependency_regression.py --mode audit

dep-diff:
	cd backend && $(PYTHON) scripts/run_dependency_regression.py --mode diff

dep-validate:
	cd backend && $(PYTHON) scripts/run_dependency_regression.py --mode validate --dry-run

ci-pr:
	cd backend && $(RUFF) check .
	cd backend && $(RUFF) format --check .
	cd backend && $(MYPY) app
	cd backend && $(PYTEST) -m unit -v
	cd backend && $(PYTEST) -m contract -v
	cd backend && $(PYTEST) -m security -v
	cd backend && $(PYTEST) -m "integration and not slow" -v
	cd backend && $(PYTEST) tests/evals/test_rag_regression.py tests/evals/test_canary_leakage.py -v
	cd backend && $(PYTEST) tests/e2e/test_e2e_business_workflows.py -v -m "critical_e2e and not live_external"
	$(PYTHON) scripts/run_bruno_tests.py --suite smoke --auto-start
	cd backend && $(PYTHON) scripts/run_performance_benchmark.py --mode smoke --fail-on-regression
	cd backend && $(PYTHON) scripts/run_dependency_regression.py --mode validate --dry-run --fail-on-breakage

ci-main:
	cd backend && $(RUFF) check .
	cd backend && $(RUFF) format --check .
	cd backend && $(MYPY) app
	cd backend && $(PYTEST) -m unit -v
	cd backend && $(PYTEST) -m contract -v
	cd backend && $(PYTEST) -m security -v
	cd backend && $(PYTEST) -m integration -v
	cd backend && $(PYTEST) -m ai -v
	cd backend && $(PYTEST) -m "e2e and not live_external" -v
	$(PYTHON) scripts/run_bruno_tests.py --suite full --auto-start
	cd backend && $(PYTHON) scripts/run_performance_benchmark.py --mode smoke --fail-on-regression
	cd backend && $(PYTHON) scripts/run_dependency_regression.py --mode audit
	cd backend && $(PYTHON) scripts/run_dependency_regression.py --mode validate --fail-on-breakage
	cd backend && $(PYTEST) --cov=app --cov-branch tests/ -v --cov-report=xml:coverage.xml --cov-fail-under=85
	cd backend && $(PYTHON) scripts/check_coverage_diff.py --min-line 85 --min-patch 80

ci-report:
	$(PYTHON) scripts/ci_failure_reporter.py --report-dirs backend/reports backend/benchmark-results --output-dir backend/reports/summary

flaky-check:
	cd backend && $(PYTHON) scripts/ci_flaky_tracker.py --check-ledger reports/flaky/flaky-tests.json

audit:
	cd backend && $(PIP_AUDIT) -r requirements.txt

sast:
	cd backend && $(BANDIT) -c pyproject.toml -r app/

openapi:
	cd backend && $(PYTHON) -m app.main --export-openapi openapi.json

docker-up:
	docker compose up -d

docker-down:
	docker compose down

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/htmlcov backend/.coverage backend/openapi.json
