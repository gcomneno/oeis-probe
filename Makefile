.PHONY: hygiene test

hygiene:
	python -m ruff check . --fix
	python -m ruff format .

test:
	python -m pytest -q
