# Project commands. AGENTS.md says to run `make lint` and `make test` before every commit.
# `make check` runs exactly what the pre-commit hook runs, over every tracked file.

.PHONY: setup lint format check typecheck test test-server server stop eval typedefs

setup:
	uv sync --all-groups
	# The global core.hooksPath delegates to this repo's .git/hooks, so install there.
	GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0= \
		uv run pre-commit install --hook-type pre-commit --hook-type pre-push

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run yamllint .

format:
	uv run ruff check --fix .
	uv run ruff format .

check:
	uv run pre-commit run --all-files

typecheck:
	uv run pyrefly check

test:
	uv run pytest

test-server:
	uv run pytest -m server

server:
	docker compose -f docker/compose.yml up -d --wait

stop:
	docker compose -f docker/compose.yml down

eval:
	uv run vf-eval factorio-arena $(ARGS)

# Regenerate Factorio Lua API typedefs for the editor (see .luarc.json). Output is gitignored.
typedefs:
	npx -y factoriomod-debug sumneko-3rd .luals
