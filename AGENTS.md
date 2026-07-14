# Project conventions

- Package manager: `uv pip` (not pip)
- Linter: `ruff`
- Type checker: `ty`
- No unicode in source files (no em dashes, smart quotes, etc.)
- Dev dependencies go under `[project.optional-dependencies] dev`
- Before committing, run `ruff format .` and `ruff check .`
