# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

See @AGENTS.md for project architecture, conventions, gotchas, and deploy steps —
it is the source of truth; keep it updated instead of duplicating it here.
Status: rebuild complete and deployed (Contabo, https://f1.mykid.life/admin);
remaining feature ideas live in @docs/REBUILD_PLAN.md.

## Checks (same as CI)

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
uv run pytest tests/test_miniapp_api.py                      # one file
uv run pytest tests/test_miniapp_api.py::test_edit_long_summary_doesnt_overflow  # one test
uv run pytest -k translate                                   # by name
```

## Testing patterns

- Tests need **no DB tunnel, network, or LLM**: DB tests build
  `DatabaseManager("sqlite+aiosqlite://")` + `create_tables()` in a fixture.
- API tests monkeypatch the module-level `db_manager` (`src.main` or
  `src.webapp.router`) with that in-memory manager, and bypass Mini App auth via
  `app.dependency_overrides[require_admin]`. Follow `tests/test_miniapp_api.py`.
- `pytest` runs with `asyncio_mode = "auto"` — async tests/fixtures need no marker.
- Because tests use SQLite, keep model/query code portable (no Postgres-only SQL
  in paths the tests exercise); real schema changes still go through Alembic.
