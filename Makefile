.PHONY: test lint format fetch clean

test:
	uv run pytest -v

lint:
	uv run ruff check .

format:
	uv run ruff format .

fetch:
	uv run ev-finder fetch-odds

clean:
	find . -type d -name '__pycache__' -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache
	rm -f data/*.db
