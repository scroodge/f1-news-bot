---
name: add-scrape-source
description: Add or fix a website news source for the scraper by editing data/sources.yaml (no code changes) and verifying link patterns against the live site. Use when the user wants to add a site, fix a broken/disabled source, or tune which links get scraped.
---

# Add a scrape source

Sources are config-only: `data/sources.yaml` → `scrape_sources` list, consumed by
`src/collectors/web_scraper.py`. RSS feeds are separate (`RSS_FEEDS` env var,
comma-separated); Telegram channels are `TELEGRAM_CHANNELS`.

## Fields

| field | meaning |
|---|---|
| `name` | display name, also the key for per-source health tracking |
| `list_url` | listing page to scan for article links |
| `link_pattern` | substring an article URL path must contain |
| `exclude_patterns` | path substrings marking non-article pages (categories, pagination) |
| `enabled` | `false` turns it off without deleting |
| `max_articles` | cap of new articles per run (keep ~5 for politeness) |

## Steps

1. Fetch the listing page and look at real article hrefs to pick
   `link_pattern` / `exclude_patterns`:
   ```bash
   curl -sL -A 'Mozilla/5.0 (f1-news-bot)' "<list_url>" | grep -oE 'href="[^"]+"' | sort -u | head -80
   ```
   Also check `<site>/robots.txt` — the scraper honors it. A 403 / Cloudflare
   challenge means the site needs a headless browser: add it with
   `enabled: false` and a comment explaining why (see `autosport.com`).

2. Add the entry to `data/sources.yaml`, with a short comment stating when the
   patterns were verified (`# verified against the live site on YYYY-MM-DD`).

3. Dry-run the source against the live site using the scraper's own logic —
   read `src/collectors/web_scraper.py` for the current function names, then
   run a small `uv run python -c '...'` that loads the source and prints the
   matched article URLs and the extracted text length for one article. Confirm
   only real articles match and full text is extracted.

4. If parsing logic changed, add an offline case to `tests/test_web_scraper.py`
   (fixture HTML, no network), then run `uv run ruff check . && uv run pytest`.

Articles also pass the relevance filter (keywords in `data/f1_2026.yaml`), so a
source with matching links can still yield nothing if content isn't F1-relevant.
