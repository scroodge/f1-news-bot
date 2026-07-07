# 🏎️ F1 News Bot

Collects Formula 1 news from many sources, translates it into **Belarusian**
with an LLM, and publishes it to the Telegram channel
[@f1scroodge](https://t.me/f1scroodge) after human moderation in a
**Telegram Mini App**.

```
RSS feeds ─┐   keyword filter     Mini App admin clicks:
           ├─→ (dedup by URL  ──→  🌐 translate (Ollama/Claude)
Websites ──┤   + embeddings)       🔑 generate key points (Claude)
Telegram ──┘         │             ✏️ edit, ✅ approve ❌ reject
channels             ▼
               PostgreSQL: news_items.status lifecycle
        collected → processed → queued → published / rejected
                                   │
                                   ▼  rate-limited publisher (bot process)
                              Telegram channel
```

## How it works

- **Collection** — RSS feeds, config-driven website scrapers
  (`data/sources.yaml`, trafilatura full-text extraction, robots.txt,
  per-source health), and optional Telegram-channel monitoring (Telethon).
  Runs every 30 minutes; URLs dedup on insert, embeddings (bge-m3) catch
  the same story retold by another outlet.
- **Admin-triggered AI** — nothing is sent to an LLM automatically. In the
  Mini App the admin sees the raw queue ("Новыя"), picks a backend per item
  (remote Ollama qwen2.5:14b or Claude `claude-haiku-4-5` — Claude's
  Belarusian is far better), reviews/edits the result, optionally generates
  🔑 key points, then approves. Per-item token usage is stored.
- **Publishing** — approved items become `queued`; the bot process posts
  them to the channel respecting `MAX_POSTS_PER_HOUR`.
- **Moderation UI** — a Telegram Mini App served by the FastAPI app,
  authenticated with Telegram initData (HMAC) + admin allowlist. The bot's
  inline commands remain as a fallback.

## Stack

Python 3.11 · FastAPI · async SQLAlchemy + Alembic (PostgreSQL) ·
python-telegram-bot · Telethon · httpx + trafilatura · remote Ollama +
Anthropic API · uv / ruff / pytest / GitHub Actions.

## Development

```bash
uv sync
ssh -f -N -L 5433:localhost:5433 contabo   # DB tunnel (Postgres lives on the VPS)
uv run alembic upgrade head
uv run python start_local.py               # FastAPI + collectors (:8000)
uv run python telegram_bot_standalone.py   # bot + publisher

uv run ruff check . && uv run pytest       # checks
```

Configuration lives in `.env` (see [.env.example](.env.example)).
Architecture details, conventions, and gotchas: [AGENTS.md](AGENTS.md).

## Production

Deployed on a Contabo VPS at `/opt/f1-news-bot`:

```bash
docker compose --profile vps up -d --build   # app + bot + redis + postgres
```

nginx terminates TLS for the Mini App at `https://f1.mykid.life/admin`.
See the Production section of [AGENTS.md](AGENTS.md) for the deploy flow.
