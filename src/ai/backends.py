"""
Pluggable LLM backends for news analysis.

Three-stage pipeline:
1. OllamaBackend.translate() — TranslateGemma 12B, RU→BE translation
2. ClaudeBackend.polish() — Sonnet polish, fixes grammar + structures output
3. ClaudeBackend.analyze() — Haiku analysis, key points + tags + sentiment
- EmbeddingClient: always the Ollama server (bge-m3), regardless of backend.
"""

import logging
from abc import ABC, abstractmethod

import aiohttp

from ..config import settings
from .schemas import (
    ANALYSIS_PROMPT,
    EN_TRANSLATE_PROMPT,
    KEY_POINTS_PROMPT,
    LANG_LABELS,
    POLISH_PROMPT,
    SUMMARY_PROMPT,
    TRANSLATION_PROMPT,
    KeyPointsAnalysis,
    NewsAnalysis,
)

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 2000


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

    async def analyze(self, title_be: str, summary_be: str) -> NewsAnalysis:
        """Analyze already-translated BE text. Raises on failure."""
        raise NotImplementedError(f"{self.name} does not support analyze()")

    async def generate_key_points(self, title_be: str, summary_be: str) -> list[str]:
        raise NotImplementedError(f"{self.name} does not support key-points generation")

    @abstractmethod
    async def check_health(self) -> bool: ...

    async def close(self) -> None:  # noqa: B027 — optional hook, not abstract
        pass


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
                headers=self._headers(), timeout=aiohttp.ClientTimeout(total=600)
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

    async def translate(self, title: str, content: str, source_lang: str = "ru") -> str:
        """Translate article to raw Belarusian text. Uses chunking for long content."""
        session = await self._get_session()
        total_tokens = {"prompt_tokens": 0, "completion_tokens": 0}
        source_label = LANG_LABELS.get(source_lang, "з іншай мовы")

        if len(content) <= MAX_CONTENT_CHARS:
            raw = await self._translate_chunk(session, title, content, total_tokens, source_label)
            self.last_usage = total_tokens
            return raw

        chunks = self._split_content(content, MAX_CONTENT_CHARS)
        logger.info(f"TG12B: translating {len(chunks)} chunk{'s' if len(chunks) != 1 else ''} ({len(content)} chars, {source_lang})")

        title_be = await self._translate_chunk(session, "", f"Загаловак: {title}", total_tokens, source_label)
        title_be = title_be.replace("Загаловак:", "").strip()

        chunk_results = []
        for i, chunk in enumerate(chunks):
            logger.info(f"TG12B: chunk {i + 1}/{len(chunks)} ({len(chunk)} chars)")
            result = await self._translate_chunk(session, "", chunk, total_tokens, source_label)
            chunk_results.append(result)

        raw = f"Назва: {title_be}\n\nТэкст:\n" + "\n\n".join(chunk_results)
        self.last_usage = total_tokens
        return raw

    def _split_content(self, text: str, max_chars: int) -> list[str]:
        """Split text into chunks at paragraph boundaries, falling back to sentence breaks."""
        paragraphs = text.split("\n\n")
        chunks = []
        current = ""
        for para in paragraphs:
            if len(current) + len(para) + 2 > max_chars and current:
                chunks.append(current.strip())
                current = para
            elif len(para) > max_chars:
                if current:
                    chunks.append(current.strip())
                current = ""
                for sentence in para.replace(". ", ".\n").split("\n"):
                    if len(current) + len(sentence) + 1 > max_chars and current:
                        chunks.append(current.strip())
                        current = sentence
                    else:
                        current = current + " " + sentence if current else sentence
            else:
                current = current + "\n\n" + para if current else para
        if current.strip():
            chunks.append(current.strip())
        return chunks

    async def _translate_chunk(
        self, session: aiohttp.ClientSession, title: str, content: str, usage: dict, source_label: str = "з рускай (ru)"
    ) -> str:
        """Translate a single chunk via Ollama API."""
        if title:
            prompt_text = TRANSLATION_PROMPT.format(source_lang=source_label, title=title, content=content)
        else:
            prompt_text = f"Перакладзі гэты тэкст на беларускую мову ({source_label}). Захавай поўную даўжыню, не скарачай:\n\n{content}"
        # Scale num_predict: ~2 tokens per char, with headroom
        num_predict = min(8192, max(2048, len(content) * 2))
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt_text}],
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": num_predict},
        }
        async with session.post(f"{self.base_url}/api/chat", json=payload) as response:
            response.raise_for_status()
            data = await response.json()
        usage["prompt_tokens"] += data.get("prompt_eval_count", 0)
        usage["completion_tokens"] += data.get("eval_count", 0)
        return data.get("message", {}).get("content", "")

    async def generate_summary(self, content: str) -> str:
        """Generate a short 2-3 sentence summary of Belarusian text via TG12B."""
        session = await self._get_session()
        truncated = content[:MAX_CONTENT_CHARS] if len(content) > MAX_CONTENT_CHARS else content
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": SUMMARY_PROMPT.format(content=truncated)}],
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 256},
        }
        async with session.post(f"{self.base_url}/api/chat", json=payload) as response:
            response.raise_for_status()
            data = await response.json()
        return data.get("message", {}).get("content", "")

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
            max_tokens=4096,
            messages=[{"role": "user", "content": POLISH_PROMPT.format(raw_be=raw_be)}],
        )
        text = response.content[0].text
        title_be = ""
        lines = text.split("\n")
        in_text = False
        collected = []
        for line in lines:
            if line.startswith("Загаловак:"):
                title_be = line[len("Загаловак:") :].strip()
            elif line.startswith("Тэкст:"):
                in_text = True
                rest = line[len("Тэкст:") :].strip()
                if rest:
                    collected.append(rest)
                continue
            elif in_text:
                collected.append(line)
        summary_be = "\n".join(collected).strip()
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

    async def translate_en(self, title: str, content: str) -> tuple[str, str]:
        """Translate English article directly to polished Belarusian via Sonnet."""
        response = await self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            messages=[
                {
                    "role": "user",
                    "content": EN_TRANSLATE_PROMPT.format(title=title, content=content),
                }
            ],
        )
        text = response.content[0].text
        lines = text.split("\n")
        title_be = ""
        in_text = False
        collected = []
        for line in lines:
            if line.startswith("Загаловак:"):
                title_be = line[len("Загаловак:") :].strip()
            elif line.startswith("Тэкст:"):
                in_text = True
                rest = line[len("Тэкст:") :].strip()
                if rest:
                    collected.append(rest)
                continue
            elif in_text:
                collected.append(line)
        self.last_usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
        }
        return title_be or "Без загалоўка", "\n".join(collected).strip()

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

    async def check_health(self) -> bool:
        try:
            await self.client.models.retrieve(self.model)
            return True
        except Exception as e:
            logger.error(f"Claude health check failed: {e}")
            return False

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
