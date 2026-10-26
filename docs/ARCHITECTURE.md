# Architecture (current state)

Snapshot of how f1-news-bot works today, written 2026-07-05 as the baseline for
the rebuild ([REBUILD_PLAN.md](REBUILD_PLAN.md)).

## Data flow

1. **Collection** (`src/collectors/`, every `CHECK_INTERVAL_MINUTES`, default 30)
   - `RSSCollector`: fetches each feed with aiohttp, parses with feedparser,
     takes ≤10 entries per feed, extracts image/video URLs from enclosures.
     Default feeds: f1news.ru, f1-world.ru, BBC Sport F1.
   - `TelegramCollector`: Telethon client with a *user* account session
     (`telegram_session.session`), scrapes messages from channels listed in
     `TELEGRAM_CHANNELS` since the last N hours. Self-disables when
     `TELEGRAM_API_ID/HASH/PHONE` are missing.
   - `RedditCollector`: stub, always disabled.
   - `NewsCollector` fans out to all collectors, then `db_manager.save_news_item`
     inserts rows; the unique constraint on `url` is the dedup mechanism.

2. **Relevance filtering** (`base_collector.py` + keyword lists in `src/config.py`)
   - Pure keyword matching against `F1_KEYWORDS` (EN+RU),
     `HIGH_PRIORITY_KEYWORDS`, `TEAM_NAMES`, `DRIVER_NAMES`.
   - Items below `MIN_RELEVANCE_SCORE` (default 0.1) are dropped by the moderator.

3. **AI processing** (`src/ai/`, every 5 min, batch of 10)
   - Language detection = Cyrillic-character ratio (>30% ⇒ Russian).
   - **Russian news**: `process_russian_news_fast` — no LLM at all; heuristic
     tags/relevance/importance, summary = truncated content.
   - **Foreign news**: Ollama (`OLLAMA_MODEL`, e.g. llama3) via raw HTTP
     `/api/generate`: translate to Russian, then a JSON-producing analysis
     prompt (summary, key_points, sentiment, importance 1–5, tags).
     `_parse_ollama_response` scrapes JSON out of free-form model text.
   - Result is written back to `news_items` (processed=true) and pushed to the
     Redis moderation queue.

4. **Moderation & publication** (`telegram_bot_standalone.py` → `src/telegram_bot/bot.py`)
   - Admin-only bot (checks `TELEGRAM_ADMIN_ID`). Syncs the Redis queue into an
     in-memory pending dict every ~30 s.
   - Commands: `/start /help /status /queue /publish /view /published`; inline
     buttons for publish / reject / edit-field / delete / pagination.
   - Publishing sends the formatted message (with media when present) to
     `TELEGRAM_CHANNEL_ID`, marks the row published, moves it to
     `published_news_items`.
   - Rate limit: `MAX_POSTS_PER_HOUR` (default 5) in `publication_scheduler.py`.

5. **API** (`src/main.py`, FastAPI :8000)
   - `GET /health`, `GET /api/stats`, `GET /api/news`
   - `POST /api/collect-news | process-news | moderate-news | schedule-publication`
     (manual triggers for the background jobs)

## Storage

- **PostgreSQL** (sync SQLAlchemy 2.0, no migrations — `create_all` at startup)
  - `news_items`: raw + processed + translated fields in one wide table;
    `url` UNIQUE.
  - `published_news_items`: denormalized copy plus publication metadata
    (`telegram_message_id`, counters).
- **Redis**
  - `f1_news:moderation_queue` (list, FIFO) — processed items awaiting the admin.
  - `f1_news:published`, `f1_news:stats` — recent history / counters.

## Deployment

- `docker-compose.yml`: `redis`, `f1-news-main` (runs `start_local.py`),
  `f1-news-telegram` (runs `telegram_bot_standalone.py`). PostgreSQL and Ollama
  are expected **on the host** (`host.docker.internal`).
- `run_all.py` runs both processes locally without Docker.
- Telethon auth is interactive-once: `setup_telegram_api.py` locally or
  `setup_telegram_docker.sh` for the container; produces
  `telegram_session.session` which is volume-mounted.

## Known problems (why we're rebuilding)

1. **Dead publication path in `main.py`** — `_schedule_publication_background`
   builds a dict and then reads `.success` off it; unreachable in practice
   because publishing moved to the bot process. Should be deleted.
2. **`bot.py` monolith** — 1670 lines, mixes UI, state, Redis sync, publishing.
3. **Config hacks** — `rss_feeds_str`/`rss_feeds_raw` double-fields with manual
   `os.environ` reads inside properties to dodge pydantic list parsing.
4. **Stale domain data** — 2022-era teams/drivers in keyword lists; keyword
   relevance is crude (score 0.1 threshold ⇒ almost everything passes).
5. **Fragile LLM integration** — hand-rolled HTTP + regex-ish JSON extraction;
   no structured output, no retries/backoff, silent fallbacks that fabricate
   neutral metadata.
6. **Sync DB in async app** — blocking SQLAlchemy calls inside asyncio loops;
   duplicated wide tables instead of a status column; no Alembic.
7. **Zero tests / CI / lint**; deps pinned to late 2023; two near-duplicate
   env example files (`.env.example`, `config.env.example`).
8. **State duplication** — the same queue lives in PostgreSQL, Redis, and the
   bot's in-memory dict, reconciled by polling.
