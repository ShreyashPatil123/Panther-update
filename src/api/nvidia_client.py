"""NVIDIA NIM API Client for chat completions."""
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from loguru import logger


class NVIDIAClient:
    """Client for NVIDIA NIM API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        timeout: float = 300.0,
    ):
        """Initialize NVIDIA API client.

        Args:
            api_key: NVIDIA API key
            base_url: API base URL
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        self.client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        logger.info(f"NVIDIA Client initialized with base URL: {base_url}")

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "nvidia/kimi-k-2.5",
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        top_p: float = 1.0,
    ) -> AsyncIterator[str]:
        """Send chat completion request to NVIDIA NIM API.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model identifier
            stream: Whether to stream response
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter

        Yields:
            Response chunks if streaming, else full response
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "stream": stream,
        }

        logger.debug(f"Sending request to {model} (stream={stream})")

        try:
            if stream:
                async with self.client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=payload,
                ) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]
                            if data.strip() == "[DONE]":
                                break

                            try:
                                import json

                                chunk = json.loads(data)
                                if "choices" in chunk and len(chunk["choices"]) > 0:
                                    delta = chunk["choices"][0].get("delta", {})
                                    if "content" in delta:
                                        yield delta["content"]
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse JSON: {data}")
                                continue
            else:
                response = await self.client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                if "choices" in data and len(data["choices"]) > 0:
                    content = data["choices"][0]["message"].get("content", "")
                    yield content

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in chat completion: {e}")
            raise

    async def validate_api_key(self) -> bool:
        """Test if API key is valid.

        Returns:
            True if API key is valid, False otherwise
        """
        try:
            messages = [{"role": "user", "content": "Hi"}]
            _ = ""
            async for chunk in self.chat_completion(
                messages,
                stream=False,
                max_tokens=10,
            ):
                _ += chunk
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error("Invalid API key")
            else:
                logger.error(f"Validation failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False

    async def list_models(self) -> List[Dict[str, Any]]:
        """Fetch available models from NVIDIA API.

        Returns:
            List of model information dictionaries
        """
        try:
            response = await self.client.get(f"{self.base_url}/models")
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            return []

    def get_available_models(self) -> List[str]:
        """Get list of commonly available NVIDIA models.

        Returns:
            List of model identifiers
        """
        return [
            "nvidia/kimi-k-2.5",
            "nvidia/kimi-k-2",
            "nvidia/llama-3.1-405b-instruct",
            "nvidia/llama-3.1-70b-instruct",
            "nvidia/llama-3.1-8b-instruct",
            "nvidia/mistral-large",
            "nvidia/codellama-70b",
        ]

    async def close(self):
        """Close HTTP client and cleanup resources."""
        await self.client.aclose()
        logger.info("NVIDIA Client closed")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
