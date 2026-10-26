---
name: deploy
description: Deploy the current main branch to the Contabo VPS (git pull + docker compose rebuild + Alembic migrations) and verify it's healthy. Use when the user asks to deploy, ship, roll out, or update production.
disable-model-invocation: true
---

# Deploy to Contabo

Production lives at `/opt/f1-news-bot` on the `contabo` SSH host. It's a git
clone of this repo; deploys are pull-based — whatever is on `origin/main` ships.

## 1. Pre-flight (local)

```bash
git status --short            # must be clean
git fetch && git status -sb   # local main must not be ahead of origin (push first, with the user's OK)
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

Stop and report if checks fail. Note whether `alembic/versions/` changed since
the deployed commit — that decides step 3:

```bash
DEPLOYED=$(ssh contabo 'cd /opt/f1-news-bot && git rev-parse HEAD')
git diff --stat "$DEPLOYED" origin/main -- alembic/versions/
```

## 2. Pull and rebuild

```bash
ssh contabo 'cd /opt/f1-news-bot && git pull && docker compose --profile vps up -d --build'
```

Always pass `--profile vps` — without it the Postgres container is not part of
the project and compose may treat it as orphaned.

## 3. Migrations (only if step 1 showed new revisions)

```bash
ssh contabo 'cd /opt/f1-news-bot && docker compose run --rm f1-news-main alembic upgrade head'
ssh contabo 'cd /opt/f1-news-bot && docker compose restart f1-news-main f1-news-telegram'
```

## 4. Verify

```bash
ssh contabo 'cd /opt/f1-news-bot && docker compose --profile vps ps'
ssh contabo 'curl -fsS http://127.0.0.1:8010/health'          # API_PORT=8010 on the VPS
curl -fsS -o /dev/null -w '%{http_code}\n' https://f1.mykid.life/admin
ssh contabo 'cd /opt/f1-news-bot && docker compose logs --tail=50 f1-news-main f1-news-telegram'
```

Report the deployed commit (`git rev-parse --short HEAD` on the VPS), container
states, and any errors in the logs. Never edit `/opt/f1-news-bot/.env` or run
destructive DB commands without explicit confirmation.
