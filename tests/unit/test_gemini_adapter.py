"""Unit tests for Gemini LLM adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_capital.adapters.llm.gemini import GeminiLLMAdapter


class TestGeminiLLMAdapter:
    """Test GeminiLLMAdapter initialization and methods."""

    def test_init_requires_api_key(self):
        with patch("agentic_capital.adapters.llm.gemini.settings") as mock_settings:
            mock_settings.gemini_api_key = ""
            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                GeminiLLMAdapter(api_key="")

    def test_init_with_explicit_key(self):
        with patch("agentic_capital.adapters.llm.gemini.genai") as mock_genai:
            adapter = GeminiLLMAdapter(api_key="test-key")
            mock_genai.Client.assert_called_once_with(api_key="test-key")
            assert adapter._generation_model == "gemini-2.5-flash"
            assert adapter._embedding_model == "text-embedding-004"

    def test_init_custom_models(self):
        with patch("agentic_capital.adapters.llm.gemini.genai"):
            adapter = GeminiLLMAdapter(
                api_key="test-key",
                generation_model="gemini-2.5-pro",
                embedding_model="text-embedding-005",
            )
            assert adapter._generation_model == "gemini-2.5-pro"
            assert adapter._embedding_model == "text-embedding-005"

    @pytest.mark.asyncio
    async def test_generate(self):
        with patch("agentic_capital.adapters.llm.gemini.genai") as mock_genai:
            mock_response = MagicMock()
            mock_response.text = "Hello world"
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            adapter = GeminiLLMAdapter(api_key="test-key")
            result = await adapter.generate("Say hello", system="You are helpful")

            assert result == "Hello world"
            mock_client.aio.models.generate_content.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_empty_response(self):
        with patch("agentic_capital.adapters.llm.gemini.genai") as mock_genai:
            mock_response = MagicMock()
            mock_response.text = None
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            adapter = GeminiLLMAdapter(api_key="test-key")
            result = await adapter.generate("test")
            assert result == ""

    @pytest.mark.asyncio
    async def test_embed(self):
        with patch("agentic_capital.adapters.llm.gemini.genai") as mock_genai:
            mock_embedding = MagicMock()
            mock_embedding.values = [0.1, 0.2, 0.3]
            mock_result = MagicMock()
            mock_result.embeddings = [mock_embedding]
            mock_client = MagicMock()
            mock_client.aio.models.embed_content = AsyncMock(return_value=mock_result)
            mock_genai.Client.return_value = mock_client

            adapter = GeminiLLMAdapter(api_key="test-key")
            result = await adapter.embed("test text")

            assert result == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_generate_raises_on_error(self):
        with patch("agentic_capital.adapters.llm.gemini.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(
                side_effect=RuntimeError("API error")
            )
            mock_genai.Client.return_value = mock_client

            adapter = GeminiLLMAdapter(api_key="test-key")
            with pytest.raises(RuntimeError, match="API error"):
                await adapter.generate("test")
