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
