# AGENTS.md — F1 News Bot

Guidance for AI agents (Claude Code, etc.) working in this repository.

## What this project is

A pipeline that collects Formula 1 news, processes it with a local LLM (Ollama),
and publishes it to a Russian-language Telegram channel after human moderation.

```
RSS feeds ─┐
           ├─→ keyword filter → PostgreSQL → AI processing → Redis queue
Telegram ──┘        (dedup by URL)         (translate/summarize)   │
channels                                                           ▼
                                              admin moderates in Telegram bot
                                                           │ approve
                                                           ▼
                                                  published to channel
```

## Runtime layout — two processes

| Process | Entry point | Role |
|---|---|---|
| Main app | `src/main.py` (or `start_local.py`) | FastAPI on :8000 + background loops: collect (30 min), AI-process (5 min), monitor (5 min) |
| Moderation bot | `telegram_bot_standalone.py` | python-telegram-bot admin UI; reads Redis queue, publishes approved items to the channel |

They share **PostgreSQL** (tables `news_items`, `published_news_items`) and talk
through **Redis** (`f1_news:moderation_queue`, `f1_news:published`).
`run_all.py` starts both locally; `docker-compose.yml` runs them as separate
containers (Redis in compose; PostgreSQL and Ollama live on the host via
`host.docker.internal`).

## Key modules

- `src/config.py` — pydantic-settings `Settings` + hardcoded keyword lists
  (`F1_KEYWORDS`, `HIGH_PRIORITY_KEYWORDS`, `TEAM_NAMES`, `DRIVER_NAMES`).
  Note: RSS feeds / Telegram channels are comma-separated env strings with
  awkward `*_raw` fallback fields — handle with care.
- `src/collectors/` — `base_collector.py` (relevance scoring), `rss_collector.py`
  (aiohttp + feedparser), `telegram_collector.py` (Telethon **user** session:
  needs `TELEGRAM_API_ID/HASH/PHONE` and `telegram_session.session` file,
  created by `setup_telegram_api.py` / `setup_telegram_docker.sh`),
  `reddit_collector.py` (stub, disabled).
- `src/ai/ollama_client.py` — raw HTTP to Ollama `/api/generate`; hand-parses
  JSON out of LLM text. Russian news (>30% Cyrillic) bypasses the LLM entirely
  via fast heuristics (`process_russian_news_fast`).
- `src/telegram_bot/bot.py` — 1670-line monolith: all commands, inline-keyboard
  moderation/editing, pagination, Redis sync loop.
- `src/moderator/` — rule checks (`MIN_RELEVANCE_SCORE`) and rate limiting
  (`MAX_POSTS_PER_HOUR`, default 5).
- `src/database.py` — sync SQLAlchemy; `db_manager` singleton; URL is the
  unique dedup key. No migrations — `create_tables()` on startup.

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
- Dead code: the publication path inside `src/main.py`
  (`_schedule_publication_background`) no longer works — publishing moved to the
  standalone bot. Don't "fix" it back to life; it should be removed.
- Keyword rosters in `src/config.py` reflect ~2022 F1 (AlphaTauri, Latifi…).
- Dependencies are pinned to late-2023 versions in `requirements.txt`.
- Secrets live in `.env` (see `config.env.example` / `.env.example`); the
  Telethon session file is a credential — never commit it.

## Running

```bash
# install deps
uv sync

# local (needs PostgreSQL + Redis reachable; LLM is remote)
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

- `docs/ARCHITECTURE.md` — current-state deep dive
- `docs/REBUILD_PLAN.md` — the rebuild roadmap (this is the active project goal)
- `README.md`, `USAGE_GUIDE.md`, `LOCAL_SETUP.md`, `DOCKER_PRODUCTION.md`,
  `TELEGRAM_SETUP.md` — user-facing setup docs (Russian)
