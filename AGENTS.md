# Project conventions

- Package manager: `uv pip` (not pip)
- Linter: `ruff`
- Type checker: `ty`
- No unicode in source files (no em dashes, smart quotes, etc.)
- Dev dependencies go under `[project.optional-dependencies] dev`
- Before committing, run `ruff format . && ruff check .` (includes tests/)
- Run `uv run pytest tests/ -v` to verify all tests pass
- CI runs ruff check, ruff format --check, and pytest for Python 3.12-3.14
