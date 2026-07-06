# AGENTS.md — F1 News Bot

Guidance for AI agents (Claude Code, etc.) working in this repository.

## What this project is

A pipeline that collects Formula 1 news, processes it with a remote LLM,
and publishes it to a Telegram channel after human moderation.

```
RSS feeds ─┐   keyword filter        AI processing + rule moderation
           ├─→ (dedup by URL) ──────→ (translate/summarize/auto-reject)
Telegram ──┘         │                          │
channels             ▼                          ▼
              PostgreSQL: news_items.status lifecycle
        collected → processed → queued → published / rejected
                         │           ▲              ▲
                         ▼           │ approve      │ rate-limited
                 admin moderates in Telegram bot ───┘ publisher loop
```

**PostgreSQL is the single source of truth** — one `news_items` table with a
`status` enum. Redis carries only a "new items" wake-up signal
(`f1_news:pending_signal`); nothing depends on it.

## Runtime layout — two processes

| Process | Entry point | Role |
|---|---|---|
| Main app | `src/main.py` (or `start_local.py`) | FastAPI on :8000 + loops: collect (30 min), AI-process + rule-moderate (5 min), monitor (5 min) |
| Moderation bot | `telegram_bot_standalone.py` | admin moderation UI (approve → `queued`) + publisher loop (posts `queued` items to the channel, `MAX_POSTS_PER_HOUR`) + new-items notifications |

`run_all.py` starts both locally; `docker-compose.yml` runs them as separate
containers (Redis in compose; PostgreSQL is the dedicated container on the
Contabo VPS — local dev reaches it via `ssh -f -N -L 5433:localhost:5433 contabo`).

## Key modules

- `src/config.py` — pydantic-settings `Settings` (`LLM_*` vars, comma-separated
  list parsing) + hardcoded keyword lists (`F1_KEYWORDS`, `TEAM_NAMES`, …).
- `src/database.py` — **async** SQLAlchemy (asyncpg); `db_manager` singleton
  exposes the lifecycle API (`save_news_item`, `mark_processed`, `approve`,
  `reject`, `mark_published`, `get_by_status`, `published_in_last_hour`).
  Schema is owned by **Alembic** (`uv run alembic upgrade head`);
  `create_tables()` is for tests only.
- `src/collectors/` — `base_collector.py` (relevance scoring), `rss_collector.py`
  (aiohttp + feedparser), `telegram_collector.py` (Telethon **user** session:
  needs `TELEGRAM_API_ID/HASH/PHONE` and `telegram_session.session` file).
- `src/ai/` — `content_processor.py` (pipeline step incl. rule moderation via
  `src/moderator/content_moderator.py`), `ollama_client.py` (remote server,
  Bearer auth). Russian news (>30% Cyrillic) currently bypasses the LLM —
  slated for removal in Phase 2 (Belarusian pipeline).
- `src/telegram_bot/` — split package: `bot.py` (wiring + loops),
  `publisher.py` (channel posting + DB-computed rate limit),
  `formatting.py` (pure message builders), `handlers/commands.py`,
  `handlers/callbacks.py`, `handlers/helpers.py` (admin gate, keyboards).
- `src/webapp/` — Telegram Mini App admin panel: `auth.py` (initData HMAC
  validation + admin allowlist; `MINIAPP_DEV_MODE=true` bypasses for local
  browser testing only), `router.py` (`/admin` page + `/admin/api/*`),
  `static/index.html` (single-file frontend, Telegram WebApp SDK, Belarusian
  UI). Mounted in `src/main.py`; `MINIAPP_URL` (HTTPS) adds an open-panel
  button to the bot.
- `src/collectors/web_scraper.py` — config-driven site scraping
  (`data/sources.yaml`), trafilatura full-text extraction, robots.txt,
  per-source health with auto-disable.

## Conventions & gotchas

- **Language**: the current code and docs are Russian-oriented, but the
  rebuild target (see `docs/REBUILD_PLAN.md`) is a **Belarusian**-language
  channel — all collected news gets translated to Belarusian before
  publication. New user-facing strings should be Belarusian; code/comments
  in English.
- **Tooling (Phase 0 done)**: uv + `pyproject.toml` (no requirements.txt),
  ruff (lint+format, config in pyproject), pytest in `tests/`, GitHub Actions
  CI (`.github/workflows/ci.yml`). Run `uv run ruff check . && uv run pytest`
  before committing.
- **LLM is remote**: `LLM_BASE_URL` (Ollama-compatible server with Bearer-token
  auth via `LLM_API_KEY`), `LLM_MODEL`, `LLM_EMBEDDING_MODEL`,
  `LLM_MAX_TOKENS`. The old `OLLAMA_*` vars are gone.
- **Schema changes go through Alembic**: edit `src/database.py` models, add a
  revision in `alembic/versions/`, run `uv run alembic upgrade head` (needs the
  DB tunnel locally). Never `create_all` in production paths.
- Keyword rosters in `src/config.py` reflect ~2022 F1 (AlphaTauri, Latifi…) —
  refresh is a Phase 2 task (`data/f1_2026.yaml`).
- Editing news items from the bot was removed in Phase 1 — item editing
  arrives with the Telegram Mini App (Phase 3). `db_manager.update_fields`
  exists for that API.
- Secrets live in `.env` (see `.env.example`); the Telethon session file is a
  credential — never commit it. The Contabo Postgres credentials live in
  `/opt/f1-news-bot/.env` on the VPS.

## Running

```bash
# install deps
uv sync

# local dev: open the DB tunnel first
ssh -f -N -L 5433:localhost:5433 contabo

# apply migrations, then run both processes
uv run alembic upgrade head
uv run python run_all.py

# checks
uv run ruff check . && uv run ruff format --check . && uv run pytest

# docker
./setup_telegram_docker.sh   # one-time Telethon auth
docker compose up -d

# health check
curl http://localhost:8000/health
```

## Docs

- `docs/ARCHITECTURE.md` — pre-rebuild baseline snapshot (kept for reference;
  the post-Phase-1 layout is described in this file)
- `docs/REBUILD_PLAN.md` — the rebuild roadmap (this is the active project goal)
- `README.md`, `USAGE_GUIDE.md`, `LOCAL_SETUP.md`, `DOCKER_PRODUCTION.md`,
  `TELEGRAM_SETUP.md` — user-facing setup docs (Russian)
