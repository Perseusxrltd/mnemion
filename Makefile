# Mnemion — developer convenience targets
#
# All test targets invoke pytest through the project's own Python interpreter
# so the test suite always runs inside the correct venv regardless of which
# `pytest` or `python` is on PATH.
#
# Usage:
#   make install       – create .venv and install all deps (including test extras)
#   make test          – run the full test suite
#   make test-fast     – run tests, skip benchmark/slow/stress marks
#   make lint          – ruff check + ruff format --check
#   make format        – auto-format with ruff

PYTHON   ?= python
VENV     := .venv
VENV_PY  := $(VENV)/bin/python
# Windows: .venv/Scripts/python.exe
ifeq ($(OS),Windows_NT)
  VENV_PY := $(VENV)/Scripts/python.exe
endif

.PHONY: install test test-fast lint format clean

install:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PY) -m pip install --upgrade pip
	$(VENV_PY) -m pip install -e ".[dev]"

test:
	$(VENV_PY) -m pytest $(PYTEST_ARGS)

test-fast:
	$(VENV_PY) -m pytest -m "not benchmark and not slow and not stress" $(PYTEST_ARGS)

lint:
	$(VENV_PY) -m ruff check .
	$(VENV_PY) -m ruff format --check .

format:
	$(VENV_PY) -m ruff format .

clean:
	rm -rf $(VENV) __pycache__ .pytest_cache dist build *.egg-info
