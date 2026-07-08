"""Test LLM backends can be instantiated — catch abstract method errors."""

import pytest
from src.ai.backends import LLMBackend, OllamaBackend, ClaudeBackend, EmbeddingClient


def test_ollama_backend_can_instantiate():
    """OllamaBackend must not have any unimplemented abstract methods."""
    backend = OllamaBackend()
    assert isinstance(backend, LLMBackend)
    assert backend.name == "ollama"


def test_ollama_has_required_methods():
    backend = OllamaBackend()
    assert hasattr(backend, "translate")
    assert hasattr(backend, "generate_summary")
    assert hasattr(backend, "close")
    assert callable(backend.translate)
    assert callable(backend.generate_summary)
    assert callable(backend.close)


def test_embedding_client_can_instantiate():
    client = EmbeddingClient()
    assert hasattr(client, "embed")
    assert callable(client.embed)
    assert hasattr(client, "close")
    assert callable(client.close)


@pytest.mark.skipif(not pytest.importorskip("anthropic"), reason="anthropic not installed")
def test_claude_backend_can_instantiate():
    backend = ClaudeBackend()
    assert isinstance(backend, LLMBackend)
    assert backend.name == "claude"
    assert hasattr(backend, "polish")
    assert hasattr(backend, "analyze")
    assert hasattr(backend, "generate_key_points")
    assert callable(backend.polish)
    assert callable(backend.analyze)
    assert callable(backend.generate_key_points)
