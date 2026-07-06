# Rebuild Plan — F1 News Bot 2.0

Goal: an F1 news gathering bot that auto-collects from many sources
(RSS, Telegram channels, **website scrapers**), translates everything that is
not already **Belarusian** into Belarusian, presents items to the admin in a
**Telegram Mini App** for review, and publishes to the channel after
confirmation. Baseline problems of the current code are catalogued in
[ARCHITECTURE.md](ARCHITECTURE.md#known-problems-why-were-rebuilding).

> **Language pivot:** the old bot targeted Russian; the rebuilt channel posts
> in **Belarusian**. This kills the current "Russian news skips AI"
> optimization — now *every* item goes through the LLM (Russian and English
> sources alike get translated to Belarusian), so the fast-path heuristics in
> `ollama_client.process_russian_news_fast` are obsolete.

Strategy: **incremental rebuild in-place**, not a from-scratch rewrite. The
pipeline shape (collect → filter → process → moderate → publish) is sound;
each phase leaves the bot working.

## Environments & infrastructure (decided)

- **LLM**: remote Ollama server — no local Ollama anywhere.

  ```env
  LLM_PROVIDER=ollama
  LLM_BASE_URL=https://dev.offtech.by:8444/ollama
  LLM_MODEL=qwen2.5:14b
  LLM_EMBEDDING_MODEL=bge-m3:latest
  LLM_API_KEY=ollama
  LLM_MAX_TOKENS=512
  ```

  These `LLM_*` variables replace `OLLAMA_BASE_URL`/`OLLAMA_MODEL`. The client
  must send the API key and respect `LLM_MAX_TOKENS`; `bge-m3` is the
  embedding model for Phase 2 semantic dedup/relevance.
- **PostgreSQL**: a **dedicated Postgres container on the Contabo VPS**,
  standing up fresh for this project (this is the first deploy of
  f1-news-bot to Contabo — nothing to migrate, no reason to share the other
  project's Supabase/Supavisor pooler on that box). Local dev connects to it
  remotely over the network from day one, so there is no dev→prod data
  migration later. Redis stays local/in-compose (it's only a signal, cheap
  to run anywhere).
- **Deployment path**: develop & test on the local machine → first push
  deploys the bot to Contabo (which already runs nginx + docker for other
  projects). Docker compose ships the app containers + Redis + this
  project's own Postgres — no shared Ollama container (LLM is remote).

## Phase 0 — Foundation (tooling)

- Migrate to `pyproject.toml` + **uv** for dependency management; drop
  `requirements.txt`.
- Add **ruff** (lint+format) and **pytest**; GitHub Actions CI (lint + tests).
- Upgrade all deps to current versions (FastAPI, pydantic 2.x latest,
  python-telegram-bot 21+, telethon, SQLAlchemy 2 async).
- One `.env.example`, delete `config.env.example`; rewrite `Settings` cleanly
  (native `list[str]` parsing, no `*_raw` hacks, no `os.environ` reads in
  properties). Switch to the `LLM_*` variable scheme above; `DATABASE_URL`
  points at Contabo Postgres in every environment.

## Phase 1 — Core cleanup

- **Delete dead code**: publication path in `main.py`, reddit stub (or finish it),
  duplicated logic between `content_processor` and `ollama_client`.
- **Async SQLAlchemy** + **Alembic** migrations. Replace the duplicated
  `published_news_items` wide table with a `status` enum
  (`collected → processed → queued → published / rejected`) on one table.
- **Single source of truth for the queue**: PostgreSQL owns state; Redis (or
  Postgres LISTEN/NOTIFY) is only a wake-up signal. Kill the bot's in-memory
  pending dict.
- Split `bot.py` into modules: `handlers/commands.py`, `handlers/callbacks.py`,
  `handlers/editing.py`, `formatting.py`, `publisher.py`.
- Tests for: relevance scoring, language detection, LLM response parsing,
  queue state transitions, message formatting.

## Phase 2 — Smarter AI

- Replace raw HTTP + JSON scraping with **structured outputs** (Ollama
  `format: json_schema`) — pydantic-validated responses, retries with backoff.
  Target server is the remote instance above (qwen2.5:14b); keep prompts and
  outputs within `LLM_MAX_TOKENS=512`, so summaries must be tight.
- **Belarusian output pipeline**: detect source language → translate/rewrite
  into Belarusian → summarize/tag. Every item goes through the LLM now
  (delete the Russian fast-path).
  ⚠️ **Eval result (2026-07-05)**: quick test on the remote server —
  qwen2.5:14b produces *garbled* Belarusian (invented words, mangled driver
  names); llama3.1:8b is better but still below publishable quality. Small
  open models can't do Belarusian well (low-resource language). **Plan for
  the translation step to use the Claude API** (e.g. Haiku for cost) behind
  the pluggable backend; keep qwen for cheap non-linguistic tasks
  (tagging, relevance, importance) where its output is structured data, not
  prose. Re-run a proper 10–20 item eval to confirm before committing.
- Pluggable LLM backend behind one interface keyed by `LLM_PROVIDER`:
  `ollama` (default, remote server) and optionally `claude` for
  higher-quality Belarusian translation.
  ✅ **Done**: `src/ai/backends.py` with `OllamaBackend` + `ClaudeBackend`,
  both expose `last_usage` for token tracking. Translation uses either
  provider; key points always use Claude.
- **Semantic dedup**: embeddings via `bge-m3:latest` on the remote server to
  catch the same story from multiple sources.
  📐 **Calibration data (2026-07-06, title-only probes):** same story EN↔RU
  ≈ 0.65–0.78; same event reworded EN ≈ 0.75; *different* events about the
  same driver/weekend ≈ 0.79 — the bands overlap on short texts. Production
  embeds title+1500 chars of body (more signal), but the default threshold
  stays conservative at **0.90**: auto-reject only near-copies; borderline
  duplicates reach the admin, who rejects them in one tap. Re-tune
  `DEDUP_SIMILARITY_THRESHOLD` with real article data once the Phase 2b
  scrapers multiply sources.
- Rewrite, don't just translate: generate channel-native Belarusian posts
  with a consistent voice, emoji conventions, and hashtags.
- Refresh domain data: 2026 teams/drivers/calendar in a data file
  (`data/f1_2026.yaml`), not hardcoded lists; relevance = keywords **plus**
  embedding similarity to an "F1 news" anchor. Add Belarusian keyword forms
  alongside EN/RU.

## Phase 2b — New scrape instruments

Today's collectors only read RSS and Telegram. Add real website scrapers as
first-class collectors (same `BaseCollector` interface, one adapter per
source):

- **Fetch layer**: httpx with per-source rate limits, retries, caching of
  ETags/Last-Modified; respect robots.txt. Playwright only for JS-heavy sites
  (keep it optional — it's heavy on the VPS).
- **Extraction**: trafilatura (or readability) for full article text + lead
  image, instead of RSS summaries — full text gives the LLM much better
  material for Belarusian rewrites.
- **Candidate sources**: formula1.com news, autosport.com, motorsport.com,
  the-race.com, planetf1.com + existing RU feeds (f1news.ru). Each adapter is
  ~a page-list parser + article extractor; config-driven list in
  `data/sources.yaml` so adding a source doesn't need code changes when the
  generic extractor works.
- **Dedup matters more here**: scrapers will overlap heavily with RSS — the
  Phase 2 embedding dedup is a prerequisite for turning many sources on.
- Track per-source health (last success, error streak) and show it in the
  admin UI; auto-disable a source after N consecutive failures and alert.

## Phase 3 — Admin panel as a Telegram Mini App

**Status: IMPLEMENTED** — the Mini App is the primary moderation interface.

The moderation UI moved from inline-keyboard chat into a **Telegram Mini
App** (web app opened from the bot). The bot keeps only notifications
("5 new items awaiting review") with a button that opens the Mini App.

- Backend: FastAPI `/admin/api` endpoints — queue (raw + processed), item
  translate (Ollama/Claude), generate key points (Claude), edit, approve →
  publish, reject, stats. Auth = Telegram `initData` HMAC validation.
- Frontend: single-file vanilla JS/HTML (`static/index.html`) with
  Telegram WebApp SDK. Two sub-tabs: "Новыя" (raw) and "На модэрацыі"
  (processed). Admin flow: 🌐 translate → ✏️ edit + 🔑 key points → ✅ approve.
  Token usage (`llm_usage`) shown in card meta.
- Publishing: admin approves → `queued` → bot publisher loop posts to channel.
- The old bot moderation commands (inline keyboards) are unused — the bot
  only sends notifications with a "Open Mini App" button.

## Phase 3b — Cool features

- **Race-weekend awareness**: pull the F1 calendar (e.g. jolpica/ergast API);
  auto-post session schedules, "lights out in 1 h" reminders, results digests.
- **Daily/weekly digest**: one composed post summarizing the day's minor news
  instead of spamming the channel.
- **Breaking-news fast lane**: importance ≥ 4 pings the admin immediately
  with a direct link into the Mini App review card.
- Engagement tracking: read back message views/reactions into
  `published_news_items` counters and show per-source performance in the
  Mini App stats tab.

## Phase 4 — Ops: move to Contabo

- docker-compose gains a `postgres` service (this project's own, dedicated —
  not shared with other things on the box) alongside the app containers +
  Redis; no Ollama container (LLM stays remote). One compose file for both
  environments: locally just don't start the `postgres` service and point
  `DATABASE_URL` at the Contabo container instead
  (`docker compose up f1-news-main f1-news-telegram redis`); on the VPS start
  everything including `postgres`.
- First deploy **is** the first push to Contabo — nothing to migrate. Deploy
  to the VPS (nginx + docker already in place there for other projects);
  expose the FastAPI app (Mini App + API) through nginx with TLS on a
  dedicated subdomain.
- Copy the Telethon session file securely to the VPS (it's a credential).
- Structured JSON logging; Prometheus metrics endpoint; alert to admin chat on
  collector failures or LLM-server unreachability (it's remote — expect
  occasional network flakiness, degrade gracefully to "queue without AI").
- Backup strategy for the DB (on Contabo) and the Telethon session.

## Decisions

| Decision | Status |
|---|---|
| Channel language | **Decided**: Belarusian — everything not already Belarusian gets translated by the LLM |
| Admin UI | **Decided**: Telegram Mini App (bot keeps only notifications + publishing) |
| New sources | **Decided**: add website scrapers (formula1.com, autosport, motorsport.com, …) alongside RSS/Telegram |
| LLM backend | **Decided**: remote Ollama (`dev.offtech.by:8444/ollama`, qwen2.5:14b, bge-m3 embeddings), pluggable interface keeps a Claude API option. ✅ Claude backend implemented (`src/ai/backends.py`) — key points always use Claude, translation can use either |
| DB | **Decided**: PostgreSQL on Contabo from the beginning; local dev connects remotely |
| Hosting | **Decided**: test locally → deploy to Contabo VPS |
| Bot framework | Open: python-telegram-bot v21+ vs aiogram 3 — leaning PTB upgrade (less churn) |
| Digest cadence | Open: daily / per-session / off by default — leaning daily, configurable |
| Contabo Postgres flavor | **Decided**: dedicated plain Postgres container for the bot (own `docker-compose` service on Contabo) — this is a fresh deploy, nothing for f1-news-bot exists on the VPS yet, so no reason to deal with the other project's Supavisor pooler quirks (no TLS, tenant-suffixed users) |

## Suggested order of work

Phase 0 → Phase 1 are prerequisites and low-risk; do them first in one branch
each. In Phase 2, do the **Belarusian translation eval first** — it's the
biggest unknown and may change the LLM choice. Phase 2b scrapers should land
after embedding dedup exists (they multiply duplicates). The Phase 3 Mini App
can be developed in parallel with 2/2b since it only consumes the queue API.
Phase 3b features ship one at a time. Keep the channel running throughout —
the rebuild must never take publishing offline for more than a deploy.
