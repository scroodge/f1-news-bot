# AGENTS.md — F1 News Bot

Guidance for AI agents (Claude Code, etc.) working in this repository.

## What this project is

A pipeline that collects Formula 1 news, processes it with a remote LLM
(admin-triggered — no auto-processing), and publishes it to a Telegram
channel after human moderation in the Telegram Mini App.

```
RSS feeds ─┐   keyword filter     Mini App admin clicks:
           ├─→ (dedup by URL) ──→  🌐 translate (Ollama/Claude)
Telegram ──┘         │              🔑 generate key points (Claude)
channels             │              ✏️ edit, ✅ approve ❌ reject
                     ▼
               PostgreSQL: news_items.status lifecycle
        collected → processed → queued → published / rejected
                         │           ▲              ▲
                         ▼           │ approve      │ rate-limited
             admin moderates in      └──────────────┘ publisher loop
             Telegram Mini App                    (in bot process)
```

**PostgreSQL is the single source of truth** — one `news_items` table with a
`status` enum. Redis carries only a "new items" wake-up signal
(`f1_news:pending_signal`) that is currently **written but not consumed** —
the bot's notify loop is disabled (`_notify_loop` exists in `bot.py` but is
never started); nothing depends on Redis.

## Runtime layout — two processes

| Process | Entry point | Role |
|---|---|---|
| Main app | `src/main.py` (or `start_local.py`) | FastAPI on :8000 + loops: collect (30 min), monitor (5 min). **No auto-LLM processing** — admin triggers AI actions via the Mini App |
| Moderation bot | `telegram_bot_standalone.py` | publisher loop (posts `queued` items to the channel, `MAX_POSTS_PER_HOUR`) + inline-command fallback UI. Notify loop disabled |

`docker-compose.yml` runs them as separate containers (Redis in compose;
PostgreSQL is the dedicated container on the Contabo VPS — local dev reaches
it via `ssh -f -N -L 5433:localhost:5433 contabo`). `run_all.py` is deprecated.

## Key modules

- `src/config.py` — pydantic-settings `Settings` (`LLM_*` vars,
  `LLM_PROVIDER=ollama|claude`, category lists via comma-separated parsing).
- `src/database.py` — **async** SQLAlchemy (asyncpg); `db_manager` singleton
  exposes the lifecycle API (`save_news_item`, `mark_processed`, `approve`,
  `reject`, `mark_published`, `get_by_status`, `published_in_last_hour`,
  `get_collected_news`, `update_fields`). Schema is owned by **Alembic**
  (`uv run alembic upgrade head`); `create_tables()` is for tests only.
- `src/collectors/` — `base_collector.py` (relevance scoring), `rss_collector.py`
  (aiohttp + feedparser; uses trafilatura for full-text when summary < 300 chars),
  `telegram_collector.py` (Telethon **user** session: needs
  `TELEGRAM_API_ID/HASH/PHONE` and `telegram_session.session` file).
- `src/ai/` — `content_processor.py` (admin-triggered `translate_news()` and
  `generate_keypoints()`; also embedding dedup on first translate),
  `backends.py` (pluggable `OllamaBackend` + `ClaudeBackend`
  with `last_usage` token tracking), `schemas.py` (pydantic response models).
  `src/moderator/content_moderator.py` is **dead code** — rule-based
  auto-rejection was removed together with the auto-processing loop; nothing
  imports it (candidate for deletion or re-wiring into the translate step).
- `src/telegram_bot/` — split package: `bot.py` (wiring + loops),
  `publisher.py` (channel posting + DB-computed rate limit),
  `formatting.py` (pure message builders), `handlers/commands.py`,
  `handlers/callbacks.py`, `handlers/helpers.py` (admin gate, keyboards).
- `src/webapp/` — Telegram Mini App admin panel: `auth.py` (initData HMAC
  validation + admin allowlist; `MINIAPP_DEV_MODE=true` bypasses for local
  browser testing only), `router.py` (`/admin` page + `/admin/api/*`:
  `/queue/raw`, `/queue`, `/items/{id}/translate|generate-keypoints|edit|approve|reject`,
  `/published`, `/rejected`, `/stats`), `static/index.html` (single-file
  frontend, Telegram WebApp SDK, Belarusian UI with Новыя/На модэрацыі
  sub-tabs, translate, key points, edit, approve/reject). Mounted in
  `src/main.py`; `MINIAPP_URL` (HTTPS) adds an open-panel button to the bot.
- `src/collectors/web_scraper.py` — config-driven site scraping
  (`data/sources.yaml`), trafilatura full-text extraction, robots.txt,
  per-source health with auto-disable.

## Conventions & gotchas

- **Language**: everything not already Belarusian gets translated by the LLM.
  New user-facing strings should be Belarusian; code/comments in English.
- **Tooling**: uv + `pyproject.toml` (no requirements.txt), ruff (lint+format,
  config in pyproject), pytest in `tests/`, GitHub Actions CI
  (`.github/workflows/ci.yml`). Run `uv run ruff check . && uv run pytest`
  before committing.
- **LLM backends**: two providers keyed by `LLM_PROVIDER` (ollama or claude).
  Ollama: remote server at `LLM_BASE_URL` with Bearer `LLM_API_KEY`
  (qwen2.5:14b — its Belarusian is poor; Claude is the production choice).
  Claude: `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` (default claude-haiku-4-5).
  Translation can use either (admin picks per item in the Mini App);
  key points always use Claude. Embeddings (dedup) always use the Ollama
  server (`LLM_EMBEDDING_MODEL`, bge-m3). Both backends expose `last_usage`
  (`prompt_tokens`/`completion_tokens`) saved to the item's `llm_usage`
  JSON column.
- **Schema changes go through Alembic**: edit `src/database.py` models, add a
  revision in `alembic/versions/`, run `uv run alembic upgrade head` (needs the
  DB tunnel locally). Never `create_all` in production paths.
- **Admin-triggered AI**: no auto-processing loop. The admin clicks:
  🌐 (Ollama/Claude) to translate → item moves to "На модэрацыі" tab →
  ✏️ to edit → 🔑 to generate key points → ✅ to queue for publishing.
  Re-translate resets all AI fields (title_be, summary, key_points, tags,
  sentiment, importance). Save auto-saves edits before regenerating key points.
- Keyword rosters (relevance scoring) live in `data/f1_2026.yaml` — 2026 grid,
  en/ru/be forms — loaded by `src/config.py` at import. Roster changes are
  YAML edits, not code. Scrape sources likewise in `data/sources.yaml`.
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
uv run python start_local.py     # main app (FastAPI + collectors)
uv run python telegram_bot_standalone.py  # moderation bot

# checks
uv run ruff check . && uv run ruff format --check . && uv run pytest

# health check
curl http://localhost:8000/health
```

## Production (Contabo VPS)

- Deployed at `/opt/f1-news-bot` (git clone of this repo); `.env` there holds
  production config incl. Postgres creds (chmod 600).
- `docker compose --profile vps up -d --build` — the `vps` profile adds the
  dedicated Postgres container (`f1-news-postgres`, bound to 127.0.0.1:5433).
- Mini App is public at **https://f1.mykid.life/admin** — nginx terminates TLS
  (`/etc/nginx/sites-available/f1.mykid.life`, certbot cert) and proxies to
  the app container on 127.0.0.1:8010 (`API_PORT=8010`; host port 8000 is
  taken by Kong). Channel: `@f1scroodge`.
- Deploy an update: `ssh contabo 'cd /opt/f1-news-bot && git pull && docker
  compose --profile vps up -d --build'` (+ `docker compose run --rm
  f1-news-main alembic upgrade head` when there are new migrations).

## Docs

- `docs/ARCHITECTURE.md` — pre-rebuild baseline snapshot (kept for reference)
- `docs/REBUILD_PLAN.md` — the rebuild roadmap (completed & deployed 2026-07-06;
  kept for the remaining feature ideas: digest, race-calendar integration)
- `README.md`, `USAGE_GUIDE.md`, `LOCAL_SETUP.md`, `DOCKER_PRODUCTION.md`,
  `TELEGRAM_SETUP.md` — user-facing setup docs (Russian, some outdated)
