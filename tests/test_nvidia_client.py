"""Tests for NVIDIA API client."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, AsyncMock

from src.api.nvidia_client import NVIDIAClient


@pytest.fixture
def client():
    """Create a test client."""
    return NVIDIAClient(api_key="test_key", base_url="https://api.test.com/v1")


async def async_gen(items):
    """Helper to create async generator."""
    for item in items:
        yield item


@pytest.mark.asyncio
async def test_client_initialization(client):
    """Test client initialization."""
    assert client.api_key == "test_key"
    assert client.base_url == "https://api.test.com/v1"
    assert client.client is not None


@pytest.mark.asyncio
async def test_chat_completion_stream(client):
    """Test streaming chat completion via mocked HTTP."""
    lines = [
        'data: {"choices":[{"delta":{"content":"Hello"}}]}',
        'data: {"choices":[{"delta":{"content":" world"}}]}',
        'data: [DONE]',
    ]

    # Build an async context manager that simulates the streaming response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()  # sync
    mock_response.request = MagicMock()

    # aiter_lines must be a regular method returning an async generator
    def fake_aiter_lines():
        return async_gen(lines)

    mock_response.aiter_lines = fake_aiter_lines

    # The context manager wrapping the streaming call
    mock_stream_cm = MagicMock()
    mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

    with patch.object(client.client, 'stream', return_value=mock_stream_cm):
        chunks = []
        async for chunk in client.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            stream=True,
        ):
            chunks.append(chunk)

        assert chunks == ["Hello", " world"]


@pytest.mark.asyncio
async def test_validate_api_key_success(client):
    """Test API key validation success."""
    with patch.object(
        client, 'chat_completion', return_value=async_gen(["Hello"])
    ):
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
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [
            {"id": "model1"},
            {"id": "model2"},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    async def fake_get(*args, **kwargs):
        return mock_response

    with patch.object(client.client, 'get', side_effect=fake_get):
        models = await client.list_models()
        assert len(models) == 2
