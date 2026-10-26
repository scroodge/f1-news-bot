# F1 News Bot — Architecture & Walkthrough

> Comprehensive documentation of the current production system (post-rebuild, deployed 2026-07-06).

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Database Schema & Status Lifecycle](#3-database-schema--status-lifecycle)
4. [Process 1: Main App](#4-process-1-main-app)
5. [Collection Pipeline](#5-collection-pipeline)
6. [Relevance Scoring](#6-relevance-scoring)
7. [AI Processing Pipeline](#7-ai-processing-pipeline)
8. [Mini App Admin Panel](#8-mini-app-admin-panel)
9. [Process 2: Moderation Bot](#9-process-2-moderation-bot)
10. [Configuration Reference](#10-configuration-reference)
11. [Workflow Examples](#11-workflow-examples)
12. [Testing](#12-testing)
13. [Deployment](#13-deployment)
14. [Key Decisions & Gotchas](#14-key-decisions--gotchas)

---

## 1. Project Overview

**F1 News Bot** is a pipeline that collects Formula 1 news from RSS feeds, Telegram channels, and websites; processes it with a remote LLM (admin-triggered — no auto-processing); and publishes it to a Telegram channel after human moderation in the Telegram Mini App.

### Technology Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Python 3.11, asyncio |
| HTTP framework | FastAPI (Uvicorn) |
| Database | PostgreSQL 17 (asyncpg), SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Cache / signal | Redis 7 (wake-up signal only, not consumed) |
| Bot framework | python-telegram-bot v21+ |
| Telegram client | Telethon (user session for channel scraping) |
| LLM backends | Ollama (remote, TG12B + bge-m3) / Anthropic Claude (Sonnet + Haiku) |
| Formatting / lint | Ruff, uv |
| Testing | pytest-asyncio, httpx, SQLite |
| CI | GitHub Actions |
| Deployment | Docker Compose, nginx |
| Secret management | `.env` (pydantic-settings) |

### Two-Process Architecture

The system runs as **two independent processes** connected only through the PostgreSQL database:

```
┌──────────────────────────────────────┐  ┌──────────────────────────────────────┐
│         PROCESS 1: MAIN APP          │  │      PROCESS 2: MODERATION BOT       │
│         (start_local.py)             │  │     (telegram_bot_standalone.py)     │
│                                      │  │                                      │
│  FastAPI server on port :8000        │  │  python-telegram-bot polling          │
│                                      │  │                                      │
│  Loops:                              │  │  Loop:                               │
│    • Collection (every 30 min)       │  │    • Publisher (every 60 sec)        │
│    • Monitoring (every 5 min)        │  │    • (Notify loop — disabled)        │
│                                      │  │                                      │
│  Exposes:                            │  │  Exposes:                            │
│    • /health, /api/*                 │  │    • Bot commands (7 handlers)       │
│    • /admin (Mini App panel)         │  │    • Inline button callbacks         │
│    • /admin/api/* (REST endpoints)   │  │                                      │
└──────────────┬───────────────────────┘  └──────────────┬───────────────────────┘
               │                                         │
               │         SINGLE SOURCE OF TRUTH          │
               │         ┌─────────────────────┐         │
               └─────────┤    PostgreSQL       ├─────────┘
                         │   news_items table  │
                         │   (status-driven)   │
                         └─────────────────────┘
                                    │
                         ┌──────────┴──────────┐
                         │    Redis             │
                         │  f1_news:           │
                         │  pending_signal      │
                         │  (written but NOT    │
                         │   consumed)          │
                         └─────────────────────┘
```

**PostgreSQL is the single source of truth** — all queue state lives in the `news_items` table with a `status` enum. Redis carries only a "new items" wake-up signal that is written but not consumed (the notify loop exists in `bot.py` but is never started; nothing depends on Redis).

---

## 2. System Architecture

### Component Diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL DEPENDENCIES                               │
├────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────────────────┐   │
│  │ RSS Feeds   │  │ Telegram API     │  │ Ollama Server                │   │
│  │ f1news.ru   │  │ (Telethon user   │  │ dev.offtech.by:8444          │   │
│  │ f1-world.ru │  │  session)        │  │  • qwen2.5:14b               │   │
│  │ BBC Sport   │  │ @f1news etc.     │  │  • translategemma:12b        │   │
│  └──────┬──────┘  └────────┬─────────┘  │  • bge-m3 (embedding)        │   │
│         │                  │            └──────────────┬───────────────┘   │
│         │                  │                           │                   │
│         ▼                  ▼                           ▼                   │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │                   PROCESS 1: MAIN APP                              │    │
│  │  ┌─────────────────────────────────────────────────────────────┐   │    │
│  │  │  F1NewsBotApp (main.py)                                     │   │    │
│  │  │                                                              │   │    │
│  │  │  ┌─────────────────┐   ┌────────────────┐   ┌────────────┐  │   │    │
│  │  │  │ FastAPI Routes   │   │ Collection     │   │ Monitoring │  │   │    │
│  │  │  │ • /health        │   │ Loop (30 min)  │   │ Loop (5min)│  │   │    │
│  │  │  │ • /api/*         │   │                │   │            │  │   │    │
│  │  │  │ • /admin (Mini   │   │ NewsCollector──┼──►│ db_manager │  │   │    │
│  │  │  │   App frontend)  │   │  │  │  │       │   │ .ping()    │  │   │    │
│  │  │  │ • /admin/api/*   │   │  │  │  │       │   └────────────┘  │   │    │
│  │  │  └─────────────────┘   │  │  │  │                            │   │    │
│  │  │                        │  ▼  ▼  ▼                            │   │    │
│  │  │                        │ RSS  TG  Web                         │   │    │
│  │  │                        │ Coll Coll Scraper                    │   │    │
│  │  │                        └──────────────────────────────────────┘   │    │
│  │  │                                                              │   │    │
│  │  │  ┌─────────────────────────────────────────────────────┐     │   │    │
│  │  │  │  WebApp (src/webapp/)                               │     │   │    │
│  │  │  │  ┌──────────┐  ┌────────────┐  ┌────────────────┐  │     │   │    │
│  │  │  │  │ auth.py  │  │ router.py │  │ static/        │  │     │   │    │
│  │  │  │  │ initData │  │ REST API  │  │ index.html     │  │     │   │    │
│  │  │  │  │ HMAC     │  │ endpoints │  │ (Telegram      │  │     │   │    │
│  │  │  │  │ validate │  │           │  │  WebApp SDK)   │  │     │   │    │
│  │  │  │  └──────────┘  └────────────┘  └────────────────┘  │     │   │    │
│  │  │  └─────────────────────────────────────────────────────┘     │   │    │
│  │  └─────────────────────────────────────────────────────────────┘   │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │                    PROCESS 2: MODERATION BOT                        │    │
│  │  ┌─────────────────────────────────────────────────────────────┐   │    │
│  │  │  F1NewsBot (bot.py)                                        │   │    │
│  │  │                                                              │   │    │
│  │  │  ┌─────────────────┐   ┌────────────────┐                  │   │    │
│  │  │  │ Bot Commands    │   │ Publisher Loop  │                  │   │    │
│  │  │  │ /start /help    │   │ (every 60 sec)  │                  │   │    │
│  │  │  │ /status /queue  │   │                 │                  │   │    │
│  │  │  │ /view /publish  │   │ can_publish? ──►│                  │   │    │
│  │  │  │ /published      │   │ next_queued ──►│                  │   │    │
│  │  │  │                 │   │ format_post ──►│                  │   │    │
│  │  │  │ Handlers:       │   │ send_message──►│                  │   │    │
│  │  │  │ commands.py     │   │ mark_published │                  │   │    │
│  │  │  │ callbacks.py    │   └────────────────┘                  │   │    │
│  │  │  │ helpers.py      │                                       │   │    │
│  │  │  └─────────────────┘                                       │   │    │
│  │  └─────────────────────────────────────────────────────────────┘   │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │  SHARED COMPONENTS (used by both processes)                        │    │
│  │                                                              │    │    │
│  │  ┌────────────┐  ┌──────────────┐  ┌──────────────┐         │    │    │
│  │  │ database.py│  │ config.py    │  │ models.py    │         │    │    │
│  │  │ (async     │  │ (pydantic    │  │ (Pydantic    │         │    │    │
│  │  │ SQLAlchemy)│  │  Settings)   │  │  DTOs)       │         │    │    │
│  │  └────────────┘  └──────────────┘  └──────────────┘         │    │    │
│  │                                                              │    │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │    │    │
│  │  │ ai/          │  │ collectors/  │  │ services/    │       │    │    │
│  │  │ • backends.py│  │ • base       │  │ • redis_     │       │    │    │
│  │  │ • content_   │  │ • rss        │  │   service.py │       │    │    │
│  │  │   processor  │  │ • telegram   │  │              │       │    │    │
│  │  │ • dedup.py   │  │ • web_scraper│  │              │       │    │    │
│  │  │ • schemas.py │  │ • news_      │  │              │       │    │    │
│  │  │              │  │   collector  │  │              │       │    │    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘       │    │    │
│  └─────────────────────────────────────────────────────────────┘    │    │
└────────────────────────────────────────────────────────────────────────────┘
```

### Directory Layout

```
src/
├── main.py                    # FastAPI app: F1NewsBotApp class
├── config.py                  # Settings (pydantic-settings)
├── database.py                # DatabaseManager + NewsItemDB ORM
├── models.py                  # Pydantic DTOs
├── ai/
│   ├── backends.py            # OllamaBackend, ClaudeBackend, EmbeddingClient
│   ├── content_processor.py   # translate_news(), generate_keypoints()
│   ├── dedup.py               # cosine_similarity(), find_duplicate()
│   └── schemas.py             # NewsAnalysis, KeyPointsAnalysis + prompts
├── collectors/
│   ├── base_collector.py      # BaseCollector ABC (relevance scoring)
│   ├── news_collector.py      # NewsCollector orchestrator
│   ├── rss_collector.py       # RSSCollector (feedparser + trafilatura)
│   ├── telegram_collector.py  # TelegramCollector (Telethon)
│   └── web_scraper.py         # WebScraperCollector (httpx + trafilatura)
├── moderator/
│   └── content_moderator.py   # DEAD CODE (rule-based auto-rejection, unused)
├── services/
│   └── redis_service.py       # RedisService (wake-up signal only)
├── telegram_bot/
│   ├── bot.py                 # F1NewsBot wiring + loops
│   ├── publisher.py           # Publisher (rate-limited channel posting)
│   ├── formatting.py          # Pure formatting functions
│   └── handlers/
│       ├── commands.py        # /start /help /status /queue /view /publish /published
│       ├── callbacks.py       # Inline button callbacks
│       └── helpers.py         # Admin gate, keyboards, pagination
├── utils/
│   ├── logger.py              # ColoredFormatter + JSONFormatter
│   ├── monitor.py             # SystemMonitor (health checks)
│   └── timezone.py            # pytz utilities
└── webapp/
    ├── auth.py                # initData HMAC validation
    ├── router.py              # FastAPI router
    └── static/
        └── index.html         # Single-file frontend (Telegram WebApp SDK)
```

---

## 3. Database Schema & Status Lifecycle

### The `news_items` Table

PostgreSQL is the **single source of truth** — one wide table with all fields.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID (PK) | Auto-generated |
| `title` | String | Original title (RU/EN) |
| `content` | Text | Full article text |
| `url` | String (UNIQUE) | Source URL — the dedup key |
| `source` | String | Source name |
| `source_type` | String | `rss` / `telegram` / `web` |
| `published_at` | DateTime | Original article publication date |
| `relevance_score` | Float | 0.0–1.0 keyword relevance |
| `keywords` | JSON | Extracted F1 keywords |
| `status` | NewsStatus enum | Lifecycle state (see below) |
| `created_at` | DateTime | When collected |
| `image_url` | String? | Lead image URL |
| `video_url` | String? | Video URL |
| `media_type` | String? | `photo` / `video` |
| `summary` | Text? | Short BE summary for channel post |
| `key_points` | JSON | List of bullet points (BE) |
| `sentiment` | String | `positive` / `negative` / `neutral` |
| `importance_level` | Integer | 1–5 |
| `formatted_content` | Text? | Formatted post body |
| `tags` | JSON | List of BE hashtags |
| `translated_title` | Text? | Belarusian title |
| `translated_summary` | Text? | Belarusian full text |
| `translated_key_points` | JSON | Belarusian key points |
| `original_language` | String? | `be` / `ru` / `en` / `unknown` |
| `rejected_reason` | String? | Why rejected |
| `moderated_at` | DateTime? | When moderated (approved or rejected) |
| `telegram_message_id` | Integer? | Telegram message ID after publishing |
| `published_to_channel_at` | DateTime? | When published to channel |
| `embedding` | JSON? | bge-m3 vector for semantic dedup |
| `llm_usage` | JSON? | Token usage per AI step |

### Status Lifecycle

```
                    ┌──────────┐
                    │COLLECTED │  ←- NewsCollector.save_news_item()
                    └────┬─────┘
                         │
                    [translate_news() — admin clicks 🌐]
                         │
                    ┌────▼──────┐
                    │ PROCESSED │  ←- ContentProcessor.mark_processed()
                    └────┬──────┘
                         │
              ┌──────────┼──────────┐
              │          │          │
         [approve()] [edit()] [generate_keypoints()]
              │          │          │
              │     (stays PROCESSED)
              │          │
         ┌────▼────┐     │
         │  QUEUED │     │
         └────┬────┘     │
              │          │
         [mark_published() — Publisher loop]
              │          │
         ┌────▼──────┐   │
         │ PUBLISHED │   │
         └───────────┘   │
                         │
                    ┌────▼──────┐
                    │ REJECTED  │  ←- from any status except PUBLISHED
                    └───────────┘
                         ▲
                    (also from COLLECTED
                     via bulk-reject)
```

**Valid transitions** (enforced by `DatabaseManager._transition()`):

| Transition | From → To | When |
|-----------|-----------|------|
| `save_news_item` | — → `COLLECTED` | Collection loop inserts new item |
| `mark_processed` | `COLLECTED` → `PROCESSED` | AI translation completes |
| `approve` | `PROCESSED` → `QUEUED` | Admin clicks ✅ in Mini App |
| `reject` | any (except `PUBLISHED`) → `REJECTED` | Admin clicks ❌ |
| `mark_published` | `QUEUED` → `PUBLISHED` | Publisher posts to channel |
| `reject_all_collected` | `COLLECTED` → `REJECTED` | Admin bulk-rejects in "Новыя" tab |
| `reject_all_pending` | `PROCESSED` → `REJECTED` | Admin bulk-rejects in "На модэрацыі" tab |

### Alembic Migrations

Schema changes go through Alembic. Current migrations:

| File | Description |
|------|-------------|
| `0001_initial_schema.py` | Single `news_items` table with status enum |
| `0002_add_embedding.py` | Add `embedding` JSON column |
| `0003_add_llm_usage.py` | Add `llm_usage` JSON column |

Apply: `uv run alembic upgrade head` (requires DB tunnel locally).

---

## 4. Process 1: Main App

### Entry Point

**`start_local.py`** creates and runs the FastAPI application:

```python
app, db_manager, settings = create_app()
```

`create_app()` builds the `F1NewsBotApp` instance which:
1. Initializes `DatabaseManager` (async SQLAlchemy via asyncpg)
2. Configures CORS middleware
3. Mounts the webapp router (`/admin` + `/admin/api/*`)
4. Registers FastAPI routes (`/health`, `/api/stats`, `/api/news`, `/api/collect-news`)
5. Starts background tasks (asyncio.create_task):
   - **Collection loop** (`_collection_loop`): every `CHECK_INTERVAL_MINUTES` (default 30), calls `NewsCollector.collect_all_news()`
   - **Monitoring loop** (`_monitoring_loop`): every 5 minutes, runs `SystemMonitor` health checks

### FastAPI Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/health` | GET | System health (DB, Redis, Ollama) |
| `/api/stats` | GET | Aggregate statistics by status |
| `/api/news` | GET | Paginated news items |
| `/api/collect-now` | POST | Manual trigger: run collection immediately |

The `/admin` namespace is handled by the webapp router (see [section 8](#8-mini-app-admin-panel)).

### Background Loop Details

**Collection loop** (`_collection_loop`):
```python
async def _collection_loop(self):
    while True:
        try:
            if await db_manager.ping():
                collector = NewsCollector(db_manager)
                stats = await collector.collect_all_news()
                logger.info(f"Collection complete: {stats}")
        except Exception as e:
            logger.error(f"Collection error: {e}")
        await asyncio.sleep(CHECK_INTERVAL_MINUTES * 60)
```

**Monitoring loop** (`_monitoring_loop`):
```python
async def _monitoring_loop(self):
    while True:
        monitor = SystemMonitor(settings)
        report = await monitor.run_all_checks()
        if report.has_warnings:
            logger.warning(f"Health issues: {report.warnings}")
        await asyncio.sleep(5 * 60)
```

---

## 5. Collection Pipeline

### Orchestrator: `NewsCollector`

`NewsCollector.collect_all_news()` fans out to all active collectors concurrently:

```python
async def collect_all_news(self) -> CollectionStats:
    tasks = []
    for name, collector_cls in self.collectors.items():
        tasks.append(self._collect_from_source(name, collector_cls))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # ... aggregate stats
```

Each collector runs independently; errors in one don't affect the others.

### Collector 1: RSSCollector

**What it does**: Fetches RSS/Atom feeds, parses entries, extracts F1-related articles.

**Sources** (from `RSS_FEEDS` env var, default):
- `https://f1news.ru/news/rss/`
- `https://www.f1-world.ru/news/rss.xml`
- `https://www.bbc.com/sport/formula1/table/standings.xml` (standings — lower relevance)

**Flow per entry**:
1. Parse with `feedparser`
2. Check relevance: `_is_f1_related()` → `calculate_relevance_score()` ≥ `MIN_RELEVANCE_SCORE` (0.1)
3. If RSS summary < 300 chars → `_fetch_full_text()` via trafilatura (HTTP GET + HTML extraction)
4. Extract media: `_extract_image_url()`, `_extract_video_url()` from enclosures/media_content
5. Build `NewsItem` → `db_manager.save_news_item()`

**Limits**: max 10 entries per feed per cycle. URL unique constraint handles dedup.

### Collector 2: WebScraperCollector

**What it does**: Config-driven site scraping with robots.txt respect and per-source health tracking.

**Sources** (from `data/sources.yaml`):
- formula1.com
- the-race.com
- racefans.net
- (and others — each with `base_url`, `listing_url`, `article_selector`, `limit`)

**Flow per source**:
1. Robots.txt check (cached per host for 24h) → skip if disallowed
2. HTTP GET `listing_url` → pasre HTML → extract article links via `article_selector`
3. For each link (up to `max_articles`):
   - `db_manager.url_exists()` skip if known
   - `asyncio.sleep(1.5)` politeness delay
   - HTTP GET article → trafilatura full-text extraction
   - `calculate_relevance_score()` + `extract_keywords()`
   - → `NewsItem` → save
4. Track errors: increment `error_streak` on failure, auto-disable source after threshold

**Health report**: `collect()` returns `WebScraperHealth` with per-source `last_success`, `error_streak`, `is_disabled`.

### Collector 3: TelegramCollector

**What it does**: Monitors Telegram channels via Telethon user session.

**Requirements**: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_PHONE`, and a `telegram_session.session` file (created by `setup_telegram_api.py`).

**Flow**:
1. Start Telethon client with saved session
2. For each channel in `TELEGRAM_CHANNELS`:
   - `client.iter_messages(channel, limit=50, offset_date=24h_ago)`
   - For each message: `_is_f1_related()` → `_create_news_item()` → save
3. Self-disables when `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` / `TELEGRAM_PHONE` are missing

### Dedup Strategy

Three layers:
1. **URL uniquenes** (primary): `news_items.url` has a UNIQUE constraint; INSERT silently returns None on conflict
2. **Semantic dedup** (during translate): embedding cosine similarity ≥ 0.90 → auto-reject as "duplicate of {id}"
3. **Title/URL dedup** at collection time: `db_manager.url_exists()` check before fetching full article

---

## 6. Relevance Scoring

### How `calculate_relevance_score()` Works

Defined in `base_collector.py`. Scores each article on a 0–1 scale using keyword matching against data from `data/f1_2026.yaml`:

```python
def calculate_relevance_score(self, title: str, content: str) -> float:
    text = (title + " " + content).lower()
    score = 0.0

    # Base score: any F1 keyword match
    if any(kw in text for kw in F1_KEYWORDS):
        score = max(score, 0.3)

    # Priority boost: race results, breaking news
    if any(kw in text for kw in HIGH_PRIORITY_KEYWORDS):
        score = max(score, 0.6)

    # Team/driver boost
    if any(kw in text for kw in TEAM_NAMES + DRIVER_NAMES):
        score = max(score, 0.5)

    # Title match bonus (keywords in title → more relevant)
    title_lower = title.lower()
    title_matches = sum(1 for kw in F1_KEYWORDS if kw in title_lower)
    score += title_matches * 0.05

    # Special phrases (pole position, race winner, etc.)
    if any(phrase in text for phrase in SPECIAL_PHRASES):
        score = max(score, 0.7)

    return min(score, 1.0)
```

### Data Sources

`data/f1_2026.yaml` contains:
- **Teams**: 2026 grid teams (Red Bull, McLaren, Ferrari, Mercedes, etc.) in en/ru/be
- **Drivers**: 2026 drivers in en/ru/be
- **Keywords**: F1-specific terms (pit stop, DRS, podium, championship, etc.)
- **High priority**: race results, driver transfers, technical regulations
- **Teams & drivers point to driver-team mappings**: for tagging

### Keyword Extraction

`extract_keywords()` scans title + content for any keyword from the F1 rosters and returns deduplicated matches.

---

## 7. AI Processing Pipeline

### Overview

AI processing is **admin-triggered** — no auto-processing loop. The admin clicks action buttons in the Mini App to invoke specific AI operations per item.

### `ContentProcessor`

The central class in `src/ai/content_processor.py`. It holds references to both the Ollama and Claude backends and orchestrates the full pipeline.

### Translation Pipeline (`translate_news()`)

Called when admin clicks 🌐 in the Mini App. Option to choose provider: `ollama` or `claude`.

```
POST /admin/api/items/{id}/translate?provider=ollama

┌──────────────────────────────────────────────────────────────────┐
│  1. WARMUP                                                       │
│     If first call this session: pre-load TG12B model on         │
│     Ollama server with a dummy request to avoid cold-start lag  │
│                                                                  │
│  2. DEDUP CHECK (only when status == COLLECTED)                  │
│     EmbeddingClient.embed(title + first 1500 chars) via bge-m3  │
│     cosine_similarity() vs recent items (lookback=7 days)       │
│     If match ≥ 0.90 → auto-reject as "duplicate of {id}"        │
│                                                                  │
│  3. LANGUAGE DETECTION                                           │
│     Count Cyrillic characters in content                         │
│     > 30% → "ru", 0% → "en", otherwise → "unknown"             │
│                                                                  │
│  4. COMPRESSION (if content > 3000 chars)                        │
│     Claude Sonnet (if using claude provider)                     │
│     or skip (if using ollama — TG12B handles length)             │
│     Target: ~4000 chars, preserve key info                       │
│                                                                  │
│  5. TRANSLATE (RU/EN → Belarusian)                               │
│     Ollama path:                                                 │
│       TG12B model → raw Belarusian translation                   │
│       Chunking at paragraph boundaries if > 2000 chars           │
│     Claude path:                                                 │
│       Sonnet → direct EN→BE translation                          │
│                                                                  │
│  6. SHORT SUMMARY                                                │
│     TG12B generates 2-3 sentence summary in Belarusian           │
│                                                                  │
│  7. POLISH                                                       │
│     Claude Sonnet fixes grammar, structures output               │
│     Returns: (clean_title_be, clean_summary_be)                  │
│                                                                  │
│  8. ANALYZE                                                      │
│     Claude Haiku structured output → NewsAnalysis                │
│     Fields: key_points_be (max 3), sentiment, importance(1-5),  │
│             tags_be (max 5)                                      │
│                                                                  │
│  9. SAVE                                                         │
│     db_manager.mark_processed(item_id, processed_data, usage)    │
│     Status: COLLECTED → PROCESSED (or re-process keeps PROCESSED)│
│     llm_usage JSON saved with token counts per step              │
│                                                                  │
│  10. SIGNAL (optional, not consumed)                             │
│      redis_service.signal_new_pending()                          │
└──────────────────────────────────────────────────────────────────┘
```

### Key Points Generation (`generate_keypoints()`)

Called when admin clicks 🔑 in the Mini App on an already-translated item.

```
POST /admin/api/items/{id}/generate-keypoints

1. Load item from DB (must be PROCESSED or QUEUED)
2. Claude Haiku receives: title_be + summary_be
3. Structured output: 1-3 key points in Belarusian
4. db_manager.update_fields(item_id, key_points=[...])
```

### LLM Backend Architecture

**`OllamaBackend`** — communicates with remote Ollama server at `LLM_BASE_URL`:
- `translate()`: POST `/api/generate` with TG12B model, BE prompt
- `generate_summary()`: POST `/api/generate` with TG12B, summary prompt
- `warmup()`: POST `/api/generate` with dummy 1-token request to load model
- Chunking: splits content at `\n\n` boundaries, translates each chunk, joins
- Auth: Bearer token from `LLM_API_KEY`

**`ClaudeBackend`** — communicates with Anthropic Messages API:
- `polish()`: Sonnet model, prompt to fix grammar + structure → (title_be, summary_be)
- `analyze()`: Haiku model, structured output via system prompt → `NewsAnalysis`
- `generate_key_points()`: Haiku, key-points prompt
- `compress()`: Sonnet, compress long content preserving key facts
- `translate_en()`: Sonnet, direct EN→BE translation

**`EmbeddingClient`** — produces embeddings for dedup:
- `embed(text)`: POST `/api/embed` with bge-m3 model → vector of floats
- Always uses Ollama server regardless of `LLM_PROVIDER`

**Token tracking**: Both backends expose `last_usage` (`prompt_tokens` / `completion_tokens`) saved to the item's `llm_usage` JSON column for cost monitoring.

### Semantic Dedup

```python
# src/ai/dedup.py
def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    return dot / (norm_a * norm_b + 1e-10)

def find_duplicate(embedding, recent_embeddings, threshold=0.90):
    for existing_id, existing_emb in recent_embeddings:
        sim = cosine_similarity(embedding, existing_emb)
        if sim >= threshold:
            return existing_id
    return None
```

Recent embeddings are loaded from items in the last `DEDUP_LOOKBACK_DAYS` (7) excluding the current item.

---

## 8. Mini App Admin Panel

### Overview

The Mini App is the **primary moderation interface** — a single-file HTML/JS application served at `/admin`, authenticated via Telegram's `initData` HMAC scheme.

### Authentication (`src/webapp/auth.py`)

```python
async def require_admin(authorization: str = Header(None)) -> str:
    # "Authorization: tma <initData>"
    scheme, _, init_data = authorization.partition(" ")
    if scheme.lower() != "tma":
        raise HTTPException(401, "Invalid auth scheme")

    # Parse initData params
    data_check_string, hash_value = extract_init_data(init_data)

    # HMAC-SHA256 validation
    secret_key = hmac.new(b"WebAppData", settings.TELEGRAM_BOT_TOKEN.encode(), hashlib.sha256)
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256)

    if computed_hash.hexdigest() != hash_value:
        raise HTTPException(401, "Invalid hash")

    # Check admin ID
    user_id = parse_user_id(init_data)
    if str(user_id) != settings.TELEGRAM_ADMIN_ID:
        raise HTTPException(403, "Not authorized")
```

`MINIAPP_DEV_MODE=true` bypasses all validation (for local browser testing).

### API Endpoints

All under `/admin/api/`:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/admin` | GET | Serve `index.html` |
| `/admin/api/queue` | GET | PROCESSED items (moderation queue, paginated) |
| `/admin/api/queue/raw` | GET | COLLECTED items (raw queue, paginated) |
| `/admin/api/queue/raw/reject-all` | POST | Bulk-reject all COLLECTED items |
| `/admin/api/queue/reject-all` | POST | Bulk-reject all PROCESSED items |
| `/admin/api/items/{id}` | GET | Single item detail |
| `/admin/api/items/{id}/translate` | POST | Trigger AI translation (background task) |
| `/admin/api/items/{id}/progress` | GET | Poll translation progress |
| `/admin/api/items/{id}/generate-keypoints` | POST | Generate Claude key points |
| `/admin/api/items/{id}/edit` | POST | Edit fields: title_be, summary, key_points, tags, importance |
| `/admin/api/items/{id}/approve` | POST | PROCESSED → QUEUED |
| `/admin/api/items/{id}/reject` | POST | → REJECTED (optional reason) |
| `/admin/api/published` | GET | PUBLISHED items (paginated) |
| `/admin/api/rejected` | GET | REJECTED items (paginated) |
| `/admin/api/stats` | GET | Aggregate statistics |

### Frontend (`index.html`)

Single-file application using Telegram WebApp SDK. Key behaviors:

```
┌─────────────────────────────────────────────────────────────┐
│  Telegram Mini App: F1 News Moderation                       │
│  Language: Belarusian                                        │
│                                                             │
│  ┌──────────┬──────────────┬──────────────┬──────────────┐  │
│  │  Новыя   │ На модэрацыі │ Апублікавана │  Адхілена   │  │
│  │ (COLLECT)│  (PROCESSED) │ (PUBLISHED)  │ (REJECTED)  │  │
│  └──────────┴──────────────┴──────────────┴──────────────┘  │
│                                                             │
│  =================== Новыя (Tab 1) =================       │
│  For each COLLECTED item:                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 📰 Original title (RU/EN)                           │   │
│  │ 📝 Content preview (first 200 chars)                │   │
│  │ 🔗 Source | Relevance: 0.85 | 🇷🇺 Russian            │   │
│  │                                                      │   │
│  │  [ 🌐 Перакласці (Ollama) ]  [ 🌐 Claude ]          │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ================ На модэрацыі (Tab 2) =============       │
│  For each PROCESSED item:                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 📰 Translated title (BE)                            │   │
│  │ 📝 Belarusian summary                               │   │
│  │ 🔗 Source | 🏷️ #F1 #RedBull | 😊 positive | ⭐ 4/5 │   │
│  │                                                      │   │
│  │  [ ✏️ ] [ 🔑 Ключавыя моманты ]                      │   │
│  │  [ ✅ Апублікаваць ]  [ ❌ Адхіліць ]                │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Translation loading state:                                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  🔄 Пераклад...                                     │   │
│  │  ━━━━━━━━━━━━━━━━━━━━━━○───────────────  70%        │   │
│  │  Крок 3/5: Пераклад праз TG12B...                    │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**Frontend flow**:
1. On translate click: `POST /admin/api/items/{id}/translate` starts background task
2. Poll `GET /admin/api/items/{id}/progress` every 2 seconds
3. On complete: card auto-moves to "На модэрацыі" tab
4. All API calls include `Authorization: tma <initData>` from `Telegram.WebApp.initData`
5. Edit opens inline editor, save triggers `POST /admin/api/items/{id}/edit` (auto-saves before key points generation)

---

## 9. Process 2: Moderation Bot

### Entry Point

**`telegram_bot_standalone.py`**:

```python
async def main():
    bot = F1NewsBot()
    if await bot.initialize():
        await bot.run()
```

`initialize()` builds the `Application` (python-telegram-bot), registers handlers, resolves the channel ID from username.

### Bot Commands

| Command | Description | Implementation |
|---------|-------------|---------------|
| `/start` | Welcome message + queue count + Mini App button | `commands.py:26` |
| `/help` | Command reference | `commands.py:45` |
| `/status` | System stats (counts by status, rate limit, today/week totals) | `commands.py:60` |
| `/queue` | Paginated queue (5 items per page) with inline approve/reject/view | `commands.py:100` |
| `/view <n>` | Detail view of Nth item in queue | `commands.py:140` |
| `/publish <n>` | Approve Nth item (PROCESSED → QUEUED) | `commands.py:170` |
| `/published` | Last 10 published items | `commands.py:200` |

### Inline Callbacks

Callback data follows a `action_id` grammar:

| Callback | Action |
|----------|--------|
| `queue_<page>` | Navigate queue page |
| `view_<item_id>` | Show item detail |
| `approve_<item_id>` | Approve → QUEUED |
| `reject_<item_id>` | Reject with reason prompt |
| `delete_<item_id>` | Delete from DB entirely |
| `rejectall_confirm` / `rejectall_yes` / `rejectall_no` | Bulk reject with confirmation |
| `status_refresh` | Re-render `/status` |

### Admin Gate

```python
# helpers.py
def admin_only(func):
    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        if str(user_id) != settings.TELEGRAM_ADMIN_ID:
            await update.message.reply_text("⛔ Недазволена")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper
```

### Publisher Loop

The `Publisher` class in `publisher.py` handles rate-limited channel posting.

```
Publisher.run(stop_event) loop (every 60 seconds):

1. CHECK RATE LIMIT
   can_publish_now() → db_manager.published_in_last_hour()
   Returns True if count < MAX_POSTS_PER_HOUR (default 5)

2. DEQUEUE
   next_queued_item() → oldest QUEUED item (moderated_at ASC)
   If None → sleep 60s

3. FORMAT
   format_channel_post(item):
     - Belarusian title
     - 🔑 Key points (if any)
     - Summary body
     - Source attribution + original URL
     - Hashtags
     - Truncated to 4096 chars (Telegram limit)

4. PUBLISH
   bot.send_message(chat_id=channel_id, text=formatted, parse_mode=None)
   If media present: send_photo/send_video with caption

5. MARK PUBLISHED
   db_manager.mark_published(item.id, telegram_message_id)

6. SLEEP 60 seconds → repeat
```

**Rate limiting** is purely DB-computed — no in-memory state. The query counts items where `published_to_channel_at` is within the last hour. This means restarting the bot preserves the rate limit.

### Notify Loop (Disabled)

`_notify_loop()` exists in `bot.py` but is **never started**. It would poll Redis for the `f1_news:pending_signal` and notify the admin about new processed items. Currently unused — nothing depends on it.

### Mini App Button

When `MINIAPP_URL` (HTTPS) is configured, `/start` and `/queue` show a WebApp button:

```python
# helpers.py
def miniapp_keyboard():
    if settings.MINIAPP_URL:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("🌐 Адкрыць панэль", web_app=WebAppInfo(settings.MINIAPP_URL))
        ]])
    return None
```

---

## 10. Configuration Reference

All configuration is via environment variables (`.env` file), parsed by `pydantic-settings` in `src/config.py`.

### Core

| Variable | Default | Purpose |
|----------|---------|---------|
| `TELEGRAM_BOT_TOKEN` | `""` | Bot token from @BotFather |
| `TELEGRAM_CHANNEL_ID` | `""` | Channel to publish to (@username or numeric ID) |
| `TELEGRAM_ADMIN_ID` | `""` | Admin Telegram user ID |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5433/f1_news` | PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |

### Telegram Collection (Telethon)

| Variable | Default | Purpose |
|----------|---------|---------|
| `TELEGRAM_API_ID` | `""` | API ID from my.telegram.org |
| `TELEGRAM_API_HASH` | `""` | API hash from my.telegram.org |
| `TELEGRAM_PHONE` | `""` | Phone number for user session |
| `TELEGRAM_CHANNELS` | `""` | Comma-separated channel @usernames to monitor |

### LLM

| Variable | Default | Purpose |
|----------|---------|---------|
| `LLM_PROVIDER` | `"ollama"` | Default translation provider: `ollama` or `claude` |
| `LLM_BASE_URL` | `https://dev.offtech.by:8444/ollama` | Remote Ollama server URL |
| `LLM_MODEL` | `"qwen2.5:14b"` | General-purpose model (current min AI usage) |
| `LLM_TRANSLATION_MODEL` | `"translategemma:12b"` | Translation model (TG12B) |
| `LLM_EMBEDDING_MODEL` | `"bge-m3:latest"` | Embedding model for semantic dedup |
| `LLM_API_KEY` | `"ollama"` | Bearer token for Ollama server |
| `ANTHROPIC_API_KEY` | `""` | Anthropic API key for Claude |
| `CLAUDE_MODEL` | `"claude-haiku-4-5"` | Claude model for analysis/key points |

### Collection

| Variable | Default | Purpose |
|----------|---------|---------|
| `RSS_FEEDS` | `f1news.ru, f1-world.ru, BBC Sport F1` | Comma-separated RSS feed URLs |
| `CHECK_INTERVAL_MINUTES` | `30` | Collection loop interval |
| `MIN_RELEVANCE_SCORE` | `0.1` | Minimum relevance to accept article |

### Moderation & Publishing

| Variable | Default | Purpose |
|----------|---------|---------|
| `MAX_POSTS_PER_HOUR` | `5` | Rate limit for channel publishing |
| `DEDUP_ENABLED` | `True` | Enable semantic dedup on translate |
| `DEDUP_SIMILARITY_THRESHOLD` | `0.90` | Cosine similarity threshold for dedup |
| `DEDUP_LOOKBACK_DAYS` | `7` | Days to look back for duplicate check |

### Mini App

| Variable | Default | Purpose |
|----------|---------|---------|
| `MINIAPP_URL` | `""` | Public HTTPS URL for Mini App (must be HTTPS for Telegram) |
| `MINIAPP_DEV_MODE` | `False` | Skip Telegram auth (local dev only) |
| `MINIAPP_BOT_TOKEN` | *(from TELEGRAM_BOT_TOKEN)* | Used for initData HMAC validation |

### Domain Data

| File | Purpose |
|------|---------|
| `data/f1_2026.yaml` | F1 keywords, teams, drivers (en/ru/be) for relevance scoring |
| `data/sources.yaml` | Web scraping source configuration |

---

## 11. Workflow Examples

### Example A: Collection Cycle — "News Comes In"

This walks through one full tick of the collection loop.

**Step 1: Timer fires**

The `_collection_loop` in `main.py` wakes up. It's been 30 minutes since the last collection.

```python
# Every CHECK_INTERVAL_MINUTES (30):
await db_manager.ping()  # Check DB is alive
collector = NewsCollector(db_manager)
stats = await collector.collect_all_news()
```

**Step 2: Collectors fan out**

`NewsCollector.collect_all_news()` starts three concurrent tasks:

- **RSSCollector** → fetches 3 RSS feeds
- **WebScraperCollector** → scrapes 5 configured websites
- **TelegramCollector** → polls 2 Telegram channels

**Step 3: RSSCollector finds a story**

```
Feed: https://f1news.ru/news/rss/
Entry title: "Хэмилтон одержал победу на Гран-при Канады"
Entry summary: "Льюис Хэмилтон выиграл гонку в Монреале..."

→ _is_f1_related()? calculate_relevance_score("Хэмилтон одержал победу...")
  - "хэмилтон" in DRIVER_NAMES → boost to 0.5
  - "победу" in HIGH_PRIORITY_KEYWORDS → boost to 0.6
  - Title contains "хэмилтон" → +0.05
  - "Гран-при" in SPECIAL_PHRASES → boost to 0.7
  - Final score: 0.75 ≥ 0.1 → PASS
```

**Step 4: Fetch full text**

The RSS summary is only 180 chars (< 300), so `RSSCollector._fetch_full_text()` is called:

```python
full_text = await self._fetch_full_text("https://f1news.ru/news/2026/06/09/hamilton-wins-canada/")
# Uses trafilatura to extract article HTML → clean text
# Returns ~2500 chars of article body
```

**Step 5: Save to database**

```python
item = NewsItem(
    title="Хэмилтон одержал победу на Гран-при Канады",
    content=full_text,           # 2500 chars
    url="https://f1news.ru/news/...",
    source="f1news.ru",
    source_type="rss",
    published_at=datetime(...),
    relevance_score=0.75,
    keywords=["хэмилтон", "гран-при", "канада"],
    status=NewsStatus.COLLECTED,
)
item_id = await db_manager.save_news_item(item)
# Returns the UUID string, or None if URL already exists
```

**Step 6: WebScraperCollector finds another article**

From `data/sources.yaml`:
```yaml
- name: "The Race"
  base_url: "https://the-race.com/formula-1/"
  listing_url: "https://the-race.com/formula-1/"
  article_selector: "article a"
  max_articles: 3
```

- Robots.txt: `https://the-race.com/robots.txt` → allowed
- Fetch listing → extract 12 article links
- First one: `https://the-race.com/formula-1/2026/ferrari-new-floor/`
- Not in DB yet → politeness delay 1.5s → fetch article → trafilatura extract
- `calculate_relevance_score("Ferrari's new floor concept explained")`:
  - "ferrari" in TEAM_NAMES → 0.5
  - Final: 0.5 → PASS
- Save as COLLECTED

**Step 7: URL dedup in action**

The same article appears in both the RSS feed and the web scrape (some sites have both an RSS feed and a listing page). The second `save_news_item` hits the UNIQUE constraint on `url` and silently returns `None`. No error, no duplicate.

**Step 8: TelegramCollector finds a post**

```python
# In a channel @f1news_breaking:
# Message text: "Официально: Перес покидает Red Bull после 2026 года"
# No media, just text

→ _is_f1_related("Перес покидает Red Bull")?
  - "перес" in DRIVER_NAMES → 0.5
  - "red bull" in TEAM_NAMES → 0.5
  - Score: 0.5 → PASS

→ _create_news_item(message, channel="@f1news_breaking")
  - title = "Официально: Перес покидает Red Bull после 2026 года"
  - content = message.text
  - source = "@f1news_breaking"
  - source_type = "telegram"
  - published_at = message.date
  - media_type = None (no media)
```

**Step 9: Collection stats**

After all collectors finish, `NewsCollector` aggregates results:

```python
{
    "rss_collector": {"checked": 3, "new": 2, "skipped": 8},
    "web_scraper_collector": {"checked": 5, "new": 1, "skipped": 11},
    "telegram_collector": {"checked": 2, "new": 1, "skipped": 0},
    "total_new": 4
}
```

The DB now has 4 new items with status `COLLECTED`. The loop goes back to sleep for 30 minutes.

---

### Example B: Admin Moderates via Mini App — Full Moderation Cycle

This walks through a complete item lifecycle from collection to publication.

**Step 1: Admin opens Mini App**

Admin taps the "Open Mini App" button in the bot chat (or navigates to `https://f1.mykid.life/admin`).

```
Telegram.WebApp sends initData in Authorization header.
Backend validates HMAC-SHA256:
  secret = HMAC-SHA256("WebAppData", bot_token)
  hash = HMAC-SHA256(secret, data_check_string)
  if hash matches → user is authenticated Telegram user #{admin_id}
```

**Step 2: Admin sees "Новыя" tab with 4 items**

```
GET /admin/api/queue/raw?limit=20&offset=0
→ Returns 4 items with status=COLLECTED

Frontend renders cards:
┌────────────────────────────────────────────┐
│ 📰 Хэмилтон одержал победу на Гран-при...  │
│ 📝 Льюис Хэмилтон выиграл гонку в...      │
│ 🔗 f1news.ru | 0.75 | 🇷🇺 Русский          │
│   [ 🌐 Перакласці (TG12B) ] [ 🌐 Claude ] │
├────────────────────────────────────────────┤
│ 📰 Ferrari's new floor concept explained   │
│ 📝 The team has developed a new...         │
│ 🔗 the-race.com | 0.50 | 🇬🇧 English       │
│   [ 🌐 Перакласці (TG12B) ] [ 🌐 Claude ] │
└────────────────────────────────────────────┘
```

**Step 3: Admin clicks Translate (Ollama)**

Clicks 🌐 on the Hamilton article. Frontend sends:

```
POST /admin/api/items/{item_id_1}/translate?provider=ollama
```

Backend starts `ContentProcessor.translate_news()` as a background task:

```
1. WARMUP: Send 1 token to TG12B → model loads (~3s first call)
2. DEDUP: Embed "Хэмилтон одержал победу на Гран-при Канады..." via bge-m3
          Compare to 12 recent items (last 7 days)
          Highest match: 0.72 → below 0.90 threshold → not a duplicate
3. LANGUAGE: Content is 85% Cyrillic → detected as "ru"
4. COMPRESS: Content is 2500 chars (< 3000) → skip compression
5. TRANSLATE: TG12B prompt:
   "Перакладзі на беларускую мову (толькі мова, без тлумачэнняў):
    Хэмилтон одержал победу на Гран-при Канады..."
   → Raw output: "Хэмілтан атрымаў перамогу на Гран-пры Канады..."
6. SUMMARY: TG12B generates 2-sentence summary in Belarusian
7. POLISH (Claude Sonnet):
   Input: raw Belarusian title + summary
   Output: "Хэмілтан атрымаў перамогу на Гран-пры Канады" (fixed grammar)
   Summary: "Льюіс Хэмілтан выйграў гонку ў Манрэалі..."
8. ANALYZE (Claude Haiku):
   Input: title_be + summary_be
   Output (structured):
   {
     "key_points_be": ["Перамога Хэмілтана на Гран-пры Канады",
                       "Чацвёртая перамога ў сезоне",
                       "Выніковы разрыў — 3.2 секунды"],
     "sentiment": "positive",
     "importance_level": 4,
     "tags_be": ["F1", "Хэмілтан", "Канада", "Ferrari"]
   }
9. SAVE: db_manager.mark_processed(item_id, processed_item, llm_usage)
         → status COLLECTED → PROCESSED
         llm_usage = {
           "tg12b_translate": {"prompt_tokens": 850, "completion_tokens": 620},
           "tg12b_summary": {"prompt_tokens": 400, "completion_tokens": 120},
           "sonnet_polish": {"prompt_tokens": 300, "completion_tokens": 200},
           "haiku_analyze": {"prompt_tokens": 200, "completion_tokens": 150}
         }
```

**Step 4: Frontend polls progress**

While translating, the frontend polls every 2 seconds:

```
GET /admin/api/items/{item_id_1}/progress
→ {"step": "translating", "progress": 70, "message": "Крок 3/5: Пераклад..."}
```

When complete:

```
GET /admin/api/items/{item_id_1}/progress
→ {"step": "complete", "progress": 100}
```

The card auto-moves from "Новыя" to "На модэрацыі".

**Step 5: Admin edits the title**

In "На модэрацыі" tab, admin sees the translated card. Clicks ✏️ → inline editor opens. Admin changes:

```
translated_title: "Хэмілтан атрымаў перамогу на Гран-пры Канады"
→ "Хэмілтан зноў перамог! Гран-пры Канады"
```

Saves:

```
POST /admin/api/items/{item_id}/edit
{
  "translated_title": "Хэмілтан зноў перамог! Гран-пры Канады"
}
```

**Step 6: Admin generates key points**

Clicks 🔑. Frontend sends:

```
POST /admin/api/items/{item_id}/generate-keypoints
```

Backend: `ContentProcessor.generate_keypoints(item_id)`

```
1. Load item from DB → translated already exists
2. Claude Haiku prompt:
   "Згенеруй 1-3 ключавыя моманты (спіс) на беларускай мове для:
   Назва: Хэмілтан зноў перамог! Гран-пры Канады
   Тэкст: Льюіс Хэмілтан выйграў гонку ў Манрэалі..."
3. Response: ["Льюіс Хэмілтан атрымаў чацвёртую перамогу ў сезоне-2026",
              "Выніковы адрыў ад супернікаў склаў 3.2 секунды",
              "Гонка праходзіла ў складаных умовах"]
4. db_manager.update_fields(item_id, key_points=[...])
```

**Step 7: Admin approves**

Clicks ✅ "Апублікаваць".

```
POST /admin/api/items/{item_id}/approve
```

Backend: `db_manager.approve(item_id)`

```
Transition: PROCESSED → QUEUED
moderated_at = now()
```

Item enters the publish queue. It will be picked up by the Publisher loop in the bot process.

**Step 8: Publisher picks it up**

In the bot process, the Publisher loop ticks:

```
1. can_publish_now()? COUNT(published_to_channel_at IN last_hour) = 2
   MAX_POSTS_PER_HOUR = 5 → 2 < 5 → YES
2. next_queued_item() → oldest QUEUED item (this one)
3. format_channel_post(item):
   "🏎 Хэмілтан зноў перамог! Гран-пры Канады
   🔑 Ключавыя моманты:
   • Льюіс Хэмілтан атрымаў чацвёртую перамогу ў сезоне-2026
   • Выніковы адрыў ад супернікаў склаў 3.2 секунды
   Льюіс Хэмілтан выйграў гонку ў Манрэалі...
   🔗 f1news.ru
   https://f1news.ru/news/...
   #F1 #Хэмілтан #Канада #Ferrari"
4. bot.send_message(chat_id=@f1scroodge, text=..., parse_mode=None)
5. db_manager.mark_published(item.id, message_id=1423)
   → status QUEUED → PUBLISHED
```

**Step 9: Admin sees it published**

In the Mini App, the "Апублікавана" tab now shows the item. In the Telegram channel, followers see the post.

---

### Example C: Rate Limit in Action

This shows what happens when the publishing rate limit is hit.

```
1. Publisher loop ticks:
   COUNT(published_to_channel_at in last_hour) = 5
   MAX_POSTS_PER_HOUR = 5 → 5 < 5? NO → skip
   → Sleep 60 seconds

2. (5 more ticks over 5 minutes with nothing to publish)

3. 37 minutes later, an item that was published 61 minutes ago
   falls out of the 1-hour window:
   COUNT(published_to_channel_at in last_hour) = 4
   → can_publish_now() = YES
   → next_queued_item() → publishes next in queue

Rate limit is preserved across bot restarts (DB-computed, no in-memory state).
```

---

### Example D: Bulk Reject — "Admin Cleans Slate"

Admin wants to reject all untranslated items at once.

```
1. Admin in "Новыя" tab → clicks "Адхіліць усё" button
2. Confirmation dialog → "Вы ўпэўнены?"
3. Yes → POST /admin/api/queue/raw/reject-all
4. Backend: db_manager.reject_all_collected()
   → UPDATE news_items SET status='rejected',
        rejected_reason='Bulk rejection',
        moderated_at=NOW()
      WHERE status='collected'
5. All COLLECTED items become REJECTED
6. Frontend refreshes → empty "Новыя" tab
7. Items visible in "Адхілена" tab if admin navigates there
```

---

## 12. Testing

### Test Suite

| Test file | What it covers |
|-----------|---------------|
| `test_status_transitions.py` | Full DB lifecycle: collected→processed→queued→published/rejected, rate limit counter, URL dedup, timezone normalization. Uses `DatabaseManager("sqlite+aiosqlite://")` |
| `test_miniapp_api.py` | Mini App API endpoints — queue, raw queue, approve, reject, edit, stats, auth. Uses `httpx.AsyncClient` with `ASGITransport`, dependency overrides. Includes `test_edit_long_summary_doesnt_overflow` |
| `test_miniapp_auth.py` | initData HMAC validation: valid, tampered, wrong token, expired, missing hash, garbage input |
| `test_backends.py` | Instantiation of all LLM backends (catches missing abstract methods) |
| `test_relevance.py` | Keyword scoring: EN/RU F1 news, non-F1 news, score bounding, keyword dedup |
| `test_dedup.py` | Cosine similarity: identical vectors, orthogonal, empty, mismatched lengths; `find_duplicate` above/below threshold |
| `test_formatting.py` | Channel post formatting — BE title/labels, key points truncation, 4096 char limit, detail view, queue page |
| `test_config.py` | Settings parsing — comma-separated lists, defaults, env overrides |
| `test_html_js.py` | Validates inline JS in `index.html` with `node --check` (catches stray braces that would crash the Mini App) |
| `test_web_scraper.py` | Web scraper source loading, URL extraction |
| `test_language_detection.py` | Cyrillic ratio detection (ru/en/be) |
| `test_schemas.py` | Pydantic schema validation |

### Running Tests

```bash
uv run pytest -v          # All tests
uv run pytest tests/test_miniapp_api.py -v  # Single file
uv run pytest -k "dedup"  # By keyword
```

### CI Pipeline (`.github/workflows/ci.yml`)

```yaml
jobs:
  test:
    steps:
      - run: uv sync
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run pytest -v
```

---

## 13. Deployment

### Local Development

```bash
# 1. Install dependencies
uv sync

# 2. Open PostgreSQL tunnel (DB is on Contabo VPS)
ssh -f -N -L 5433:localhost:5433 contabo

# 3. Apply migrations
uv run alembic upgrade head

# 4. Start main app (FastAPI on :8000 + collectors)
uv run python start_local.py

# 5. In another terminal, start bot
uv run python telegram_bot_standalone.py
```

### Docker Compose

The `docker-compose.yml` runs both processes as separate containers:

```yaml
services:
  redis:
    image: redis:7-alpine

  f1-news-main:
    build: .
    command: python start_local.py
    ports: ["8000:8000"]
    depends_on: [redis]

  f1-news-telegram:
    build: .
    command: python telegram_bot_standalone.py
    depends_on: [f1-news-main]
```

A `vps` profile adds Postgres:

```yaml
services:
  postgres:
    image: postgres:17-alpine
    profiles: [vps]        # Only in VPS mode
    ports: ["127.0.0.1:5433:5432"]  # Not exposed externally
```

Run locally: `docker compose up -d --build`
Run on VPS: `docker compose --profile vps up -d --build`

### Production Topology (Contabo VPS)

```
Internet
    │
    ▼
nginx (TLS termination)
    │  /etc/nginx/sites-available/f1.mykid.life
    │  certbot SSL certificate
    ▼
127.0.0.1:8010
    │
    ▼
f1-news-main container (API_PORT=8010)
    │                        ┌─────────────────────┐
    ├──► f1-news-postgres    │ 127.0.0.1:5433       │
    │     (host: 3306)       │ dedicated container  │
    └──► redis:6379          │ (VPS profile only)   │
                             └─────────────────────┘

Host port 8000 is taken by Kong (API gateway), so API_PORT=8010.
```

### Deploying Updates

```bash
# SSH into VPS
ssh contabo

# Pull latest code, rebuild and restart
cd /opt/f1-news-bot && git pull && \
  docker compose --profile vps up -d --build

# Apply new migrations when needed
docker compose run --rm f1-news-main alembic upgrade head

# Check logs
docker compose logs -f f1-news-main
docker compose logs -f f1-news-telegram
```

### Secrets

Production `.env` at `/opt/f1-news-bot/.env` (chmod 600):
```
TELEGRAM_BOT_TOKEN=...
ANTHROPIC_API_KEY=...
DATABASE_URL=postgresql+asyncpg://f1news:...
LLM_BASE_URL=https://dev.offtech.by:8444/ollama
LLM_API_KEY=ollama
...
```

---

## 14. Key Decisions & Gotchas

### Architecture Decisions

1. **PostgreSQL as single source of truth** — all queue state lives in one `news_items` table with a status enum. No state duplication. Redis is optional (wake-up signal only, not consumed).

2. **Two independent processes** — the main app (FastAPI + collectors) and bot (telegram publisher) are separate processes that only share the database. They don't communicate directly. This means they can be deployed, scaled, and restarted independently.

3. **Admin-triggered AI** — no auto-processing loop. The admin explicitly clicks translate/key points. This avoids wasting API costs on irrelevant items and gives full editorial control.

4. **No auto-moderation** — `content_moderator.py` is dead code. Rule-based auto-rejection was removed. All moderation is manual via the Mini App.

5. **Mini App as primary UI** — the Telegram Mini App is the main moderation interface. The bot's inline commands are a fallback. The Mini App provides a richer UI with tabs, loading states, and inline editing.

6. **DB-computed rate limiting** — `published_in_last_hour()` counts from the database, not in-memory. Survives restarts. No cron or state management needed.

7. **Dual LLM backends** — Ollama (TG12B) for translation is cheaper but has poor Belarusian quality; Claude (Sonnet polish + Haiku analysis) provides production quality. Admin can choose per item.

### Gotchas & Conventions

- **Language**: Everything not already Belarusian gets translated by the LLM. New user-facing strings should be in Belarusian. Code and comments stay in English.
- **Chunking**: Long articles (>2000 chars) are split at paragraph boundaries (`\n\n`) for translation. Each chunk is translated independently, then joined.
- **Embeddings always use Ollama**: Regardless of `LLM_PROVIDER`, the dedup embedding always goes through the Ollama server (bge-m3).
- **Key points always use Claude**: Even if translation used Ollama, key point generation always calls Claude Haiku for quality.
- **Schema changes go through Alembic**: Never `create_all` in production. Edit `src/database.py` models, add a migration revision, run `alembic upgrade head`.
- **The Telethon session file is a credential**: Never commit `telegram_session.session`. It's created once via `setup_telegram_api.py`.
- **`run_all.py` is deprecated**: It launched both processes via subprocess. Use `start_local.py` and `telegram_bot_standalone.py` separately.
- **`_notify_loop` exists but is disabled**: The Redis wake-up signal is written but never consumed. Nothing depends on it.
- **Roster changes**: Update `data/f1_2026.yaml` for new drivers/teams. Code changes not needed. Scrape sources likewise in `data/sources.yaml`.
- **`.env` location**: VPS production `.env` is at `/opt/f1-news-bot/.env` (not the repo root's `.env`).
