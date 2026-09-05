.PHONY: help install dev lint format typecheck test test-cov openapi docker-up docker-down clean

PYTHON ?= python
UV ?= uv
UVICORN ?= uvicorn
PYTEST ?= pytest
RUFF ?= ruff
MYPY ?= mypy

help:
	@echo "JakeAI Platform Management Commands:"
	@echo "  make install      Install backend production and development dependencies"
	@echo "  make dev          Start local FastAPI development server with hot reload"
	@echo "  make lint         Run Ruff lint checks"
	@echo "  make format       Format code with Ruff"
	@echo "  make typecheck    Run static type analysis with Mypy"
	@echo "  make test         Execute pytest test suite"
	@echo "  make test-cov     Execute pytest with coverage report"
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
