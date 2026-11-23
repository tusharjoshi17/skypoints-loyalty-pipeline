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

snowflake-load-raw:
	snow sql -c skypoints -f sql/06_load_raw.sql

snowflake-stage-members:
	snow sql -c skypoints -f sql/07_stage_members.sql

snowflake-validate-members:
	snow sql -c skypoints -f sql/08_validate_members.sql

snowflake-publish-members:
	snow sql -c skypoints -f sql/09_publish_members.sql

snowflake-process-redemptions:
	snow sql -c skypoints -f sql/10_process_redemptions.sql

snowflake-assert:
	snow sql -c skypoints -f sql/11_assertions.sql

snowflake-run:
	$(MAKE) snowflake-load-raw
	$(MAKE) snowflake-stage-members
	$(MAKE) snowflake-validate-members
	$(MAKE) snowflake-publish-members
	$(MAKE) snowflake-process-redemptions
	$(MAKE) snowflake-assert
