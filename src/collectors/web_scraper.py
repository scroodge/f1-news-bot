"""
Website scraper collector — config-driven article scraping.

Sources live in data/sources.yaml (one listing page + link pattern per
source). For each source: fetch the listing, collect article links, skip
URLs already in the DB, then fetch and extract full article text with
trafilatura (much better LLM input than RSS snippets).

Politeness: robots.txt honored per host, descriptive User-Agent, a pause
between article fetches, per-run article cap. Health: a source that fails
several runs in a row is auto-disabled until restart and reported in stats.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
import yaml

from ..models import NewsItem, SourceType
from ..utils.timezone import utc_now
from .base_collector import BaseCollector

logger = logging.getLogger(__name__)

SOURCES_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "sources.yaml"
USER_AGENT = "F1NewsBot/2.0 (+https://github.com/scroodge/f1-news-bot)"
ARTICLE_FETCH_DELAY_SECONDS = 1.5
AUTO_DISABLE_AFTER_FAILURES = 3
MIN_ARTICLE_CHARS = 300  # shorter extractions are teasers/paywalls, not articles


@dataclass
class ScrapeSource:
    name: str
    list_url: str
    link_pattern: str
    exclude_patterns: list[str] = field(default_factory=list)
    enabled: bool = True
    max_articles: int = 5


@dataclass
class SourceHealth:
    last_success: datetime | None = None
    error_streak: int = 0
    disabled: bool = False
    last_error: str | None = None

    def record_success(self):
        self.last_success = utc_now()
        self.error_streak = 0
        self.last_error = None

    def record_failure(self, error: str):
        self.error_streak += 1
        self.last_error = error
        if self.error_streak >= AUTO_DISABLE_AFTER_FAILURES:
            self.disabled = True


def load_sources(path: Path = SOURCES_FILE) -> list[ScrapeSource]:
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return [ScrapeSource(**entry) for entry in data.get("scrape_sources", [])]
    except Exception as e:
        logger.error(f"Failed to load scrape sources from {path}: {e}")
        return []


def extract_article_links(
    html: str, list_url: str, link_pattern: str, exclude_patterns: list[str] | None = None
) -> list[str]:
    """Collect absolute article URLs matching the pattern, listing order preserved"""
    hrefs = re.findall(r'href=["\']([^"\'#]+)["\']', html)
    listing_host = urlparse(list_url).netloc
    exclude = exclude_patterns or []
    seen: set[str] = set()
    links: list[str] = []
    for href in hrefs:
        url = urljoin(list_url, href.strip())
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or parsed.netloc != listing_host:
            continue
        if link_pattern not in parsed.path:
            continue
        if any(pattern in parsed.path for pattern in exclude):
            continue
        # the listing page itself often matches its own pattern
        if url.rstrip("/") == list_url.rstrip("/"):
            continue
        if url not in seen:
            seen.add(url)
            links.append(url)
    return links


def extract_article(html: str, url: str) -> dict | None:
    """Full-text extraction via trafilatura; returns None for non-articles"""
    extracted = trafilatura.bare_extraction(html, url=url, with_metadata=True)
    if extracted is None or not (extracted.text or "").strip():
        return None
    return {
        "title": (extracted.title or "").strip(),
        "text": extracted.text.strip(),
        "image": extracted.image or None,
        "date": extracted.date or None,
    }


class WebScraperCollector(BaseCollector):
    """Scrapes configured news sites for full articles"""

    def __init__(self, sources: list[ScrapeSource] | None = None):
        super().__init__("Web Scrapers", SourceType.WEB)
        self.sources = sources if sources is not None else load_sources()
        self.health: dict[str, SourceHealth] = {s.name: SourceHealth() for s in self.sources}
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}
        self._client: httpx.AsyncClient | None = None

    async def initialize(self):
        self._client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
        )
        logger.info(f"Web scraper initialized with {len(self.sources)} sources")

    async def close(self):
        if self._client:
            await self._client.aclose()

    async def _allowed_by_robots(self, url: str) -> bool:
        host = urlparse(url).netloc
        if host not in self._robots:
            parser = robotparser.RobotFileParser()
            try:
                response = await self._client.get(f"https://{host}/robots.txt")
                if response.status_code == 200:
                    parser.parse(response.text.splitlines())
                    self._robots[host] = parser
                else:
                    self._robots[host] = None  # no robots.txt — allow
            except Exception:
                self._robots[host] = None
        parser = self._robots[host]
        return parser is None or parser.can_fetch(USER_AGENT, url)

    async def _url_known(self, url: str) -> bool:
        # Local import: keeps the module importable without a DB (tests)
        from ..database import db_manager

        try:
            return await db_manager.url_exists(url)
        except Exception:
            return False

    async def _collect_from_source(self, source: ScrapeSource) -> list[NewsItem]:
        health = self.health[source.name]
        if health.disabled:
            logger.info(f"[{source.name}] disabled after repeated failures — skipping")
            return []

        try:
            if not await self._allowed_by_robots(source.list_url):
                raise RuntimeError("listing page disallowed by robots.txt")
            response = await self._client.get(source.list_url)
            response.raise_for_status()
            # follow_redirects means the effective listing URL may differ
            effective_url = str(response.url)
            links = extract_article_links(
                response.text, effective_url, source.link_pattern, source.exclude_patterns
            )
        except Exception as e:
            health.record_failure(str(e))
            logger.error(
                f"[{source.name}] listing failed ({health.error_streak}/"
                f"{AUTO_DISABLE_AFTER_FAILURES}): {e}"
            )
            return []

        items: list[NewsItem] = []
        for url in links:
            if len(items) >= source.max_articles:
                break
            if await self._url_known(url):
                continue
            if not await self._allowed_by_robots(url):
                continue
            try:
                await asyncio.sleep(ARTICLE_FETCH_DELAY_SECONDS)
                article_response = await self._client.get(url)
                article_response.raise_for_status()
                article = extract_article(article_response.text, url)
            except Exception as e:
                logger.warning(f"[{source.name}] article fetch failed for {url}: {e}")
                continue
            if article is None or not article["title"]:
                continue
            if len(article["text"]) < MIN_ARTICLE_CHARS:
                logger.debug(f"[{source.name}] skipping short extraction: {url}")
                continue

            title, text = article["title"], article["text"]
            if not self.calculate_relevance_score(title, text):
                continue

            published_at = utc_now()
            if article["date"]:
                try:
                    published_at = datetime.fromisoformat(article["date"])
                except ValueError:
                    pass

            items.append(
                NewsItem(
                    title=title,
                    content=text,
                    url=url,
                    source=source.name,
                    source_type=SourceType.WEB,
                    published_at=published_at,
                    relevance_score=self.calculate_relevance_score(title, text),
                    keywords=self.extract_keywords(title, text),
                    image_url=article["image"],
                )
            )

        health.record_success()
        logger.info(f"[{source.name}] collected {len(items)} new articles")
        return items

    async def collect_news(self) -> list[NewsItem]:
        if self._client is None:
            await self.initialize()

        all_items: list[NewsItem] = []
        for source in self.sources:
            if not source.enabled:
                continue
            try:
                all_items.extend(await self._collect_from_source(source))
            except Exception as e:
                logger.error(f"[{source.name}] unexpected error: {e}", exc_info=True)

        self.last_check = utc_now()
        return all_items

    def get_health_report(self) -> dict[str, dict]:
        """Per-source health for stats / the future admin UI"""
        return {
            name: {
                "last_success": h.last_success.isoformat() if h.last_success else None,
                "error_streak": h.error_streak,
                "disabled": h.disabled,
                "last_error": h.last_error,
            }
            for name, h in self.health.items()
        }
