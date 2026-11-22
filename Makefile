.PHONY: install test lint format

install:
	pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check .

format:
	ruff check --fix .
	ruff format .
run:
	python -m skypoints run --input data/input --output data/output

profile:
	python -m skypoints profile-extracts data/input/extracts/* --as-of 2026-11-21

snowflake-deploy:
	snow sql -c skypoints -f sql/00_setup.sql
	snow sql -c skypoints -f sql/01_file_formats.sql
	snow sql -c skypoints -f sql/02_stage.sql
	snow sql -c skypoints -f sql/03_raw.sql
	snow sql -c skypoints -f sql/04_staging_and_audit.sql
	snow sql -c skypoints -f sql/05_core.sql
