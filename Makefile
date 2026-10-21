.PHONY: help install test lint typecheck format build publish-test publish clean all

help:
	@echo "install      - установить в editable-режиме с dev-зависимостями"
	@echo "test         - запустить тесты с покрытием"
	@echo "lint         - ruff check"
	@echo "typecheck    - mypy"
	@echo "format       - ruff format + autofix"
	@echo "build        - собрать sdist и wheel"
	@echo "publish-test - залить на TestPyPI"
	@echo "publish      - залить на PyPI"
	@echo "all          - lint + typecheck + test"

install:
	pip install -e ".[dev]"

test:
	pytest admin_cmd_runner/tests

lint:
	ruff check admin_cmd_runner tests

typecheck:
	mypy admin_cmd_runner

format:
	ruff check --fix admin_cmd_runner tests
	ruff format admin_cmd_runner tests

build: clean
	python -m build
	twine check dist/*

publish-test: build
	twine upload --repository testpypi dist/*

publish: build
	twine upload dist/*

clean:
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage

all: lint typecheck test
