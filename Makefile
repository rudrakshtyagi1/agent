.PHONY: help install test run clean

PYTHON ?= python3

help:
	@echo "AgentGuard Commands:"
	@echo "  make install   Install dependencies"
	@echo "  make test      Run test suite"
	@echo "  make run       Run backend server locally"
	@echo "  make clean     Remove cache and temporary files"

install:
	$(PYTHON) -m pip install -r backend/requirements.txt

test:
	PYTHONPATH=backend $(PYTHON) -m pytest backend/tests -v

run:
	PYTHONPATH=backend $(PYTHON) -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	rm -f backend/*.db
