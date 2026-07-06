"""
Pluggable LLM backends for news analysis.

- OllamaBackend: remote Ollama-compatible server, structured output via the
  `format` json-schema parameter on /api/chat.
- ClaudeBackend: Anthropic API via the official SDK, structured output via
  messages.parse(). Preferred for Belarusian prose quality (see
  docs/REBUILD_PLAN.md — small open models produce garbled Belarusian).
- EmbeddingClient: always the Ollama server (bge-m3), regardless of the
  analysis backend.

Selection: get_llm_backend() honors LLM_PROVIDER; "claude" falls back to
Ollama with a warning when ANTHROPIC_API_KEY is missing.
"""

import asyncio
import logging
from abc import ABC, abstractmethod

import aiohttp

from ..config import settings
from .schemas import ANALYSIS_PROMPT, KEY_POINTS_PROMPT, KeyPointsAnalysis, NewsAnalysis

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 6000  # keep prompts bounded; articles longer than this are truncated


class LLMBackend(ABC):
    """Interface for news-analysis backends"""

    name: str = "base"

    @abstractmethod
    async def analyze(self, title: str, content: str) -> NewsAnalysis:
        """Translate + analyze one news item. Raises on failure."""

    async def generate_key_points(self, title_be: str, summary_be: str) -> list[str]:
        """Generate key points from already-translated content. Default: not supported."""
        raise NotImplementedError(f"{self.name} does not support key-points generation")

    @abstractmethod
    async def check_health(self) -> bool: ...

    async def close(self) -> None:  # noqa: B027 — optional hook, not abstract
        pass

    async def analyze_with_retries(
        self, title: str, content: str, attempts: int = 3
    ) -> NewsAnalysis | None:
        """Retry wrapper with backoff; returns None when all attempts fail"""
        for attempt in range(1, attempts + 1):
            try:
                return await self.analyze(title, content[:MAX_CONTENT_CHARS])
            except Exception as e:
                logger.warning(f"[{self.name}] analysis attempt {attempt}/{attempts} failed: {e}")
                if attempt < attempts:
                    await asyncio.sleep(2**attempt)
        return None


class OllamaBackend(LLMBackend):
    """Remote Ollama-compatible server with json_schema structured output"""

    name = "ollama"

    def __init__(self):
        self.base_url = settings.llm_base_url.rstrip("/")
        self.model = settings.llm_model
        self._session: aiohttp.ClientSession | None = None

    def _headers(self) -> dict[str, str]:
        if settings.llm_api_key:
            return {"Authorization": f"Bearer {settings.llm_api_key}"}
        return {}

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self._headers(), timeout=aiohttp.ClientTimeout(total=120)
            )
        return self._session

    async def analyze(self, title: str, content: str) -> NewsAnalysis:
        session = await self._get_session()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": ANALYSIS_PROMPT.format(title=title, content=content)}
            ],
            "stream": False,
            "format": NewsAnalysis.model_json_schema(),
            "options": {
                "temperature": 0.3,
                "num_predict": settings.llm_max_tokens,
            },
        }
        async with session.post(f"{self.base_url}/api/chat", json=payload) as response:
            response.raise_for_status()
            data = await response.json()
        raw = data.get("message", {}).get("content", "")
        return NewsAnalysis.model_validate_json(raw)

    async def check_health(self) -> bool:
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/api/tags") as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


class ClaudeBackend(LLMBackend):
    """Anthropic API backend (translation quality for Belarusian)"""

    name = "claude"

    def __init__(self):
        from anthropic import AsyncAnthropic

        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.claude_model

    async def analyze(self, title: str, content: str) -> NewsAnalysis:
        response = await self.client.messages.parse(
            model=self.model,
            max_tokens=2048,
            messages=[
                {"role": "user", "content": ANALYSIS_PROMPT.format(title=title, content=content)}
            ],
            output_format=NewsAnalysis,
        )
        if response.parsed_output is None:
            raise ValueError(f"Claude returned no parseable output (stop: {response.stop_reason})")
        return response.parsed_output

    async def check_health(self) -> bool:
        try:
            # Models API round trip validates key + connectivity without sampling
            await self.client.models.retrieve(self.model)
            return True
        except Exception as e:
            logger.error(f"Claude health check failed: {e}")
            return False

    async def generate_key_points(self, title_be: str, summary_be: str) -> list[str]:
        """Generate 🔑 Галоўнае: key points from already-translated content"""
        response = await self.client.messages.parse(
            model=self.model,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": KEY_POINTS_PROMPT.format(title_be=title_be, summary_be=summary_be),
                }
            ],
            output_format=KeyPointsAnalysis,
        )
        if response.parsed_output is None:
            raise ValueError(f"Claude key-points returned no output (stop: {response.stop_reason})")
        return response.parsed_output.key_points_be

    async def close(self) -> None:
        await self.client.close()


class EmbeddingClient:
    """Embeddings via the remote Ollama server (bge-m3 — multilingual)"""

    def __init__(self):
        self.base_url = settings.llm_base_url.rstrip("/")
        self.model = settings.llm_embedding_model
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = (
                {"Authorization": f"Bearer {settings.llm_api_key}"} if settings.llm_api_key else {}
            )
            self._session = aiohttp.ClientSession(
                headers=headers, timeout=aiohttp.ClientTimeout(total=60)
            )
        return self._session

    async def embed(self, text: str) -> list[float] | None:
        """Embed one text; returns None on failure (dedup degrades gracefully)"""
        try:
            session = await self._get_session()
            payload = {"model": self.model, "input": text[:2000]}
            async with session.post(f"{self.base_url}/api/embed", json=payload) as response:
                response.raise_for_status()
                data = await response.json()
            embeddings = data.get("embeddings") or []
            return embeddings[0] if embeddings else None
        except Exception as e:
            logger.warning(f"Embedding failed (dedup will be skipped): {e}")
            return None

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


def get_llm_backend() -> LLMBackend:
    """Backend selection based on LLM_PROVIDER (+ key availability)"""
    provider = settings.llm_provider.lower()
    if provider == "claude":
        if settings.anthropic_api_key:
            logger.info(f"Using Claude backend ({settings.claude_model})")
            return ClaudeBackend()
        logger.warning(
            "LLM_PROVIDER=claude but ANTHROPIC_API_KEY is empty — falling back to Ollama"
        )
    logger.info(f"Using Ollama backend ({settings.llm_model})")
    return OllamaBackend()
