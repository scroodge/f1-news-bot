"""
Pluggable LLM backends for news analysis.

Three-stage pipeline:
1. OllamaBackend.translate() — TranslateGemma 12B, RU→BE translation
2. ClaudeBackend.polish() — Sonnet polish, fixes grammar + structures output
3. ClaudeBackend.analyze() — Haiku analysis, key points + tags + sentiment
- EmbeddingClient: always the Ollama server (bge-m3), regardless of backend.
"""

import asyncio
import logging
from abc import ABC, abstractmethod

import aiohttp

from ..config import settings
from .schemas import (
    ANALYSIS_PROMPT,
    KEY_POINTS_PROMPT,
    POLISH_PROMPT,
    TRANSLATION_PROMPT,
    KeyPointsAnalysis,
    NewsAnalysis,
)

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 6000


class LLMBackend(ABC):
    """Interface for news-analysis backends"""

    name: str = "base"

    def __init__(self):
        self.last_usage: dict = {}

    async def translate(self, title: str, content: str) -> str:
        """Translate RU article to raw Belarusian text. Raises on failure."""
        raise NotImplementedError(f"{self.name} does not support translate()")

    async def polish(self, raw_be: str) -> tuple[str, str]:
        """Polish raw BE translation. Returns (title_be, summary_be)."""
        raise NotImplementedError(f"{self.name} does not support polish()")

    @abstractmethod
    async def analyze(self, title_be: str, summary_be: str) -> NewsAnalysis:
        """Analyze already-translated BE text. Raises on failure."""

    async def generate_key_points(self, title_be: str, summary_be: str) -> list[str]:
        raise NotImplementedError(f"{self.name} does not support key-points generation")

    @abstractmethod
    async def check_health(self) -> bool: ...

    async def close(self) -> None:  # noqa: B027 — optional hook, not abstract
        pass

    async def analyze_with_retries(
        self, title_be: str, summary_be: str, attempts: int = 3
    ) -> NewsAnalysis | None:
        for attempt in range(1, attempts + 1):
            try:
                return await self.analyze(title_be, summary_be[:MAX_CONTENT_CHARS])
            except Exception as e:
                logger.warning(f"[{self.name}] analysis attempt {attempt}/{attempts} failed: {e}")
                if attempt < attempts:
                    await asyncio.sleep(2**attempt)
        return None


class OllamaBackend(LLMBackend):
    """Ollama server with TranslateGemma 12B for RU→BE translation"""

    name = "ollama"

    def __init__(self):
        super().__init__()
        self.base_url = settings.llm_base_url.rstrip("/")
        self.model = settings.llm_translation_model
        self._session: aiohttp.ClientSession | None = None

    def _headers(self) -> dict[str, str]:
        if settings.llm_api_key:
            return {"Authorization": f"Bearer {settings.llm_api_key}"}
        return {}

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self._headers(), timeout=aiohttp.ClientTimeout(total=300)
            )
        return self._session

    async def warmup(self) -> bool:
        """Pre-load the translation model with a dummy request (cold start takes ~2min)."""
        try:
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": "translate: test"}],
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": 2},
            }
            session = await self._get_session()
            async with session.post(f"{self.base_url}/api/chat", json=payload) as response:
                await response.json()
            logger.info(f"Translation model {self.model} warmed up")
            return True
        except Exception as e:
            logger.warning(f"Warmup failed (non-fatal): {e}")
            return False

    async def translate(self, title: str, content: str) -> str:
        session = await self._get_session()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": TRANSLATION_PROMPT.format(title=title, content=content)}
            ],
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 2048,
            },
        }
        async with session.post(f"{self.base_url}/api/chat", json=payload) as response:
            response.raise_for_status()
            data = await response.json()
        raw = data.get("message", {}).get("content", "")
        self.last_usage = {
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "completion_tokens": data.get("eval_count", 0),
        }
        return raw

    async def analyze(self, title_be: str, summary_be: str) -> NewsAnalysis:
        raise NotImplementedError("OllamaBackend does not support analyze() — use ClaudeBackend")

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
    """Anthropic API backend — Sonnet for polish, Haiku for analysis"""

    name = "claude"

    def __init__(self):
        super().__init__()
        from anthropic import AsyncAnthropic

        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.claude_model

    async def polish(self, raw_be: str) -> tuple[str, str]:
        """Polish raw BE translation with Sonnet. Returns (title_be, summary_be)."""
        response = await self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": POLISH_PROMPT.format(raw_be=raw_be)}
            ],
        )
        text = response.content[0].text
        title_be = ""
        summary_be = ""
        for line in text.split("\n"):
            if line.startswith("Загаловак:"):
                title_be = line[len("Загаловак:"):].strip()
            elif line.startswith("Пераказ:"):
                summary_be = line[len("Пераказ:"):].strip()
        self.last_usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
        }
        return title_be or "Без загалоўка", summary_be or "Без зместу"

    async def analyze(self, title_be: str, summary_be: str) -> NewsAnalysis:
        response = await self.client.messages.parse(
            model=self.model,
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": ANALYSIS_PROMPT.format(title_be=title_be, summary_be=summary_be),
                }
            ],
            output_format=NewsAnalysis,
        )
        if response.parsed_output is None:
            raise ValueError(f"Claude returned no parseable output (stop: {response.stop_reason})")
        result = response.parsed_output
        result.title_be = title_be
        result.summary_be = summary_be
        self.last_usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
        }
        return result

    async def check_health(self) -> bool:
        try:
            await self.client.models.retrieve(self.model)
            return True
        except Exception as e:
            logger.error(f"Claude health check failed: {e}")
            return False

    async def generate_key_points(self, title_be: str, summary_be: str) -> list[str]:
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
        self.last_usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
        }
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
