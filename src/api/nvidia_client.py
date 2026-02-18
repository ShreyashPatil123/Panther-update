"""NVIDIA NIM API Client for chat completions."""
import asyncio
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from loguru import logger

# Status codes that warrant an automatic retry
_RETRYABLE_CODES = {429, 503, 502, 504}
# Status codes that should never be retried
_NO_RETRY_CODES = {401, 403, 400, 404}


class NVIDIAClient:
    """Client for NVIDIA NIM API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        timeout: float = 300.0,
        max_retries: int = 3,
    ):
        """Initialize NVIDIA API client.

        Args:
            api_key: NVIDIA API key
            base_url: API base URL
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts for transient errors
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

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
        model: str = "meta/llama-3.1-8b-instruct",
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

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                if stream:
                    async with self.client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        json=payload,
                    ) as response:
                        # In streaming mode, must read body before
                        # raise_for_status() can access response.text
                        if response.status_code != 200:
                            await response.aread()
                            if response.status_code in _NO_RETRY_CODES:
                                response.raise_for_status()
                            if response.status_code in _RETRYABLE_CODES:
                                wait = 2 ** attempt
                                logger.warning(
                                    f"Retryable HTTP {response.status_code}, "
                                    f"attempt {attempt + 1}/{self.max_retries}, "
                                    f"waiting {wait}s"
                                )
                                await asyncio.sleep(wait)
                                last_error = httpx.HTTPStatusError(
                                    f"HTTP {response.status_code}",
                                    request=response.request,
                                    response=response,
                                )
                                continue
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
                                        # Support reasoning_content for thinking models
                                        reasoning = delta.get("reasoning_content")
                                        if reasoning:
                                            yield reasoning
                                        if delta.get("content"):
                                            yield delta["content"]
                                except json.JSONDecodeError:
                                    logger.warning(f"Failed to parse JSON: {data}")
                                    continue
                    return  # success

                else:
                    response = await self.client.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                    )
                    if response.status_code in _NO_RETRY_CODES:
                        response.raise_for_status()
                    if response.status_code in _RETRYABLE_CODES:
                        wait = 2 ** attempt
                        logger.warning(
                            f"Retryable HTTP {response.status_code}, "
                            f"attempt {attempt + 1}/{self.max_retries}, "
                            f"waiting {wait}s"
                        )
                        await asyncio.sleep(wait)
                        last_error = httpx.HTTPStatusError(
                            f"HTTP {response.status_code}",
                            request=response.request,
                            response=response,
                        )
                        continue
                    response.raise_for_status()
                    data = response.json()

                    if "choices" in data and len(data["choices"]) > 0:
                        msg = data["choices"][0]["message"]
                        content = msg.get("content") or ""
                        # Thinking models (e.g. kimi-k2-thinking, kimi-k2.5)
                        # return content=null with the answer in reasoning_content
                        if not content:
                            content = msg.get("reasoning_content") or msg.get("reasoning") or ""
                        yield content
                    return  # success

            except httpx.HTTPStatusError as e:
                if e.response.status_code in _NO_RETRY_CODES:
                    error_body = getattr(e.response, "text", str(e))
                    logger.error(f"HTTP error {e.response.status_code}: {error_body}")
                    raise
                last_error = e
                wait = 2 ** attempt
                logger.warning(
                    f"HTTP {e.response.status_code} on attempt {attempt + 1}/{self.max_retries}, "
                    f"retrying in {wait}s"
                )
                await asyncio.sleep(wait)
            except httpx.RequestError as e:
                last_error = e
                wait = 2 ** attempt
                logger.warning(
                    f"Request error on attempt {attempt + 1}/{self.max_retries}: {e}, "
                    f"retrying in {wait}s"
                )
                await asyncio.sleep(wait)
            except Exception as e:
                logger.error(f"Unexpected error in chat completion: {e}")
                raise

        # All retries exhausted
        if last_error:
            logger.error(f"All {self.max_retries} attempts failed. Last error: {last_error}")
            raise last_error

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

    async def check_health(self) -> Dict[str, Any]:
        """Check API connectivity and key validity.

        Returns:
            Dict with 'ok' (bool), 'latency_ms' (float), 'error' (str or None)
        """
        import time

        start = time.monotonic()
        try:
            response = await self.client.get(f"{self.base_url}/models")
            latency = (time.monotonic() - start) * 1000
            if response.status_code == 200:
                data = response.json()
                model_count = len(data.get("data", []))
                return {
                    "ok": True,
                    "latency_ms": round(latency, 1),
                    "model_count": model_count,
                    "error": None,
                }
            elif response.status_code == 401:
                return {
                    "ok": False,
                    "latency_ms": round(latency, 1),
                    "model_count": 0,
                    "error": "Invalid API key (401 Unauthorized)",
                }
            else:
                return {
                    "ok": False,
                    "latency_ms": round(latency, 1),
                    "model_count": 0,
                    "error": f"HTTP {response.status_code}",
                }
        except httpx.ConnectError:
            latency = (time.monotonic() - start) * 1000
            return {
                "ok": False,
                "latency_ms": round(latency, 1),
                "model_count": 0,
                "error": "Connection failed — check internet or base URL",
            }
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            return {
                "ok": False,
                "latency_ms": round(latency, 1),
                "model_count": 0,
                "error": str(e),
            }

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
        """Get list of commonly available NVIDIA NIM models.

        Returns:
            List of model identifiers
        """
        return [
            "meta/llama-3.1-8b-instruct",
            "meta/llama-3.1-70b-instruct",
            "meta/llama-3.1-405b-instruct",
            "meta/llama-3.3-70b-instruct",
            "mistralai/mistral-medium-3-instruct",
            "mistralai/mistral-7b-instruct-v0.3",
            "google/gemma-2-27b-it",
            "nvidia/llama-3.3-nemotron-super-49b-v1",
            "moonshotai/kimi-k2-instruct",
            "moonshotai/kimi-k2-thinking",
            "moonshotai/kimi-k2.5",
            "deepseek-ai/deepseek-v3.1",
            "qwen/qwq-32b",
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
