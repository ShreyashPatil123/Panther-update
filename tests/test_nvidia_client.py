"""Tests for NVIDIA API client."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.nvidia_client import NVIDIAClient


@pytest.fixture
def client():
    """Create a test client."""
    return NVIDIAClient(api_key="test_key", base_url="https://api.test.com/v1")


@pytest.mark.asyncio
async def test_client_initialization(client):
    """Test client initialization."""
    assert client.api_key == "test_key"
    assert client.base_url == "https://api.test.com/v1"
    assert client.client is not None


@pytest.mark.asyncio
async def test_chat_completion_stream(client):
    """Test streaming chat completion."""
    # Mock the response
    mock_response = AsyncMock()
    mock_response.aiter_lines.return_value = [
        'data: {"choices":[{"delta":{"content":"Hello"}}]}',
        'data: {"choices":[{"delta":{"content":" world"}}]}',
        'data: [DONE]',
    ]
    mock_response.raise_for_status = MagicMock()

    with patch.object(
        client.client, 'stream', return_value=mock_response
    ) as mock_stream:
        async with mock_stream():
            chunks = []
            async for chunk in client.chat_completion(
                messages=[{"role": "user", "content": "Hi"}],
                stream=True
            ):
                chunks.append(chunk)

            assert len(chunks) > 0


@pytest.mark.asyncio
async def test_validate_api_key_success(client):
    """Test API key validation success."""
    with patch.object(
        client, 'chat_completion', return_value=AsyncMock()
    ) as mock_chat:
        mock_chat.return_value = async_gen(["Hello"])
        result = await client.validate_api_key()
        assert result is True


@pytest.mark.asyncio
async def test_validate_api_key_failure(client):
    """Test API key validation failure."""
    with patch.object(
        client, 'chat_completion', side_effect=Exception("Invalid key")
    ):
        result = await client.validate_api_key()
        assert result is False


@pytest.mark.asyncio
async def test_list_models(client):
    """Test listing models."""
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        "data": [
            {"id": "model1"},
            {"id": "model2"},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(client.client, 'get', return_value=mock_response):
        models = await client.list_models()
        assert len(models) == 2


async def async_gen(items):
    """Helper to create async generator."""
    for item in items:
        yield item
