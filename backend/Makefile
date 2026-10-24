# Backend tasks. Run from backend/ (or `make -C backend <task>` from the repository root).
PY := .venv/bin/python
FLASK := .venv/bin/flask --app app

.PHONY: help venv dev serve init-db seed test cov lint check routes backup clean

help:
	@echo "venv      create the virtual environment and install dependencies"
	@echo "dev       run the API on http://127.0.0.1:5000 (auto-migrates the dev database, prints the setup token)"
	@echo "serve     run with gunicorn (2 workers x 4 threads) on http://127.0.0.1:5300, like production"
	@echo "init-db   create / upgrade the database"
	@echo "seed      fill an empty dev site with sample content (+ an administrator: make seed OWNER=name PASSWORD=...)"
	@echo "test      run the test suite"
	@echo "cov       tests with a coverage report"
	@echo "lint      ruff"
	@echo "check     lint + tests (what must be green before a release)"
	@echo "routes    list every route"
	@echo "backup    make a backup now"

venv:
	uv venv --python 3.12 .venv
	uv pip install --python .venv/bin/python -r pyproject.toml --extra dev

dev:
	$(FLASK) run --debug --port 5000

serve:
	.venv/bin/gunicorn -w 2 --threads 4 -b 127.0.0.1:5300 wsgi:app

init-db:
	$(FLASK) init-db

seed:
	$(FLASK) seed-demo $(if $(OWNER),--owner $(OWNER) $(if $(PASSWORD),--password $(PASSWORD)))

test:
	$(PY) -m pytest

cov:
	$(PY) -m pytest --cov=app --cov-report=term-missing

lint:
	.venv/bin/ruff check app tests

check: lint test

routes:
	$(FLASK) routes-table

backup:
	$(FLASK) backup

clean:
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
