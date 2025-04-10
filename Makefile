.DEFAULT_GOAL := help
sources = fast_grpc examples

.PHONY: .poetry  ## Check that poetry is installed
.poetry:
	@poetry -V || echo 'Please install Poetry>1.2: https://python-poetry.org/'

.PHONY: .pre-commit  ## Check that pre-commit is installed
.pre-commit:
	@pre-commit -V || echo 'Please install pre-commit: https://pre-commit.com/'

.PHONY: install  ## Install the package, dependencies, and pre-commit for local development
install: .poetry .pre-commit
	pre-commit install --install-hooks
	poetry install

.PHONY: format  ## Auto-format python source files
format: .poetry
	poetry run ruff check --fix $(sources)
	poetry run ruff format $(sources)

.PHONY: lint  ## Lint python source files
lint: .poetry
	poetry run ruff check $(sources)
	poetry run ruff format --check $(sources)
	poetry run mypy fast_grpc

.PHONY: clean  ## Clear local caches and build artifacts
clean:
	rm -rf `find . -name __pycache__`
	rm -rf .cache
	rm -rf .pytest_cache
	rm -rf .ruff_cache
	rm -rf htmlcov
	rm -rf *.egg-info
	rm -f .coverage
	rm -f .coverage.*
	rm -rf build
	rm -rf dist
	rm -rf coverage.xml
	rm -rf examples/db.sqlite3

.PHONY: help  ## Display this message
help:
	@grep -E \
		'^.PHONY: .*?## .*$$' $(MAKEFILE_LIST) | \
		sort | \
		awk 'BEGIN {FS = ".PHONY: |## "}; {printf "\033[36m%-19s\033[0m %s\n", $$2, $$3}'
