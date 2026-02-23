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
        # Fall back to default model if caller passed empty/None
        model = model or "meta/llama-3.1-8b-instruct"

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
                        headers={"Accept": "text/event-stream"},
                    ) as response:
                        # For error responses inside stream(), we must read
                        # the body first before inspecting status.
                        if response.status_code != 200:
                            await response.aread()
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
                            # Non-retryable error — log body for debugging
                            try:
                                body = response.text
                                logger.error(
                                    f"Non-retryable HTTP {response.status_code} "
                                    f"from {model}: {body[:500]}"
                                )
                            except Exception:
                                pass
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
                                        content = delta.get("content")
                                        if content:
                                            yield content
                                except json.JSONDecodeError:
                                    logger.warning(f"Failed to parse JSON: {data}")
                                    continue
                    return  # success

                else:
                    response = await self.client.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers={"Accept": "application/json"},
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
                        content = data["choices"][0]["message"].get("content", "")
                        yield content
                    return  # success

            except httpx.HTTPStatusError as e:
                if e.response.status_code in _NO_RETRY_CODES:
                    logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
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
        # Verified working as of 2026-02-23
        return [
            # --- Meta Llama ---
            "meta/llama-3.1-8b-instruct",
            "meta/llama-3.1-70b-instruct",
            "meta/llama-3.1-405b-instruct",
            "meta/llama-3.2-1b-instruct",
            "meta/llama-3.2-3b-instruct",
            "meta/llama-3.2-11b-vision-instruct",
            "meta/llama-3.2-90b-vision-instruct",
            "meta/llama-3.3-70b-instruct",
            "meta/llama-4-maverick-17b-128e-instruct",
            "meta/llama-guard-4-12b",
            "meta/llama3-70b-instruct",
            "meta/llama3-8b-instruct",
            # --- Mistral ---
            "mistralai/devstral-2-123b-instruct-2512",
            "mistralai/magistral-small-2506",
            "mistralai/mamba-codestral-7b-v0.1",
            "mistralai/mathstral-7b-v0.1",
            "mistralai/ministral-14b-instruct-2512",
            "mistralai/mistral-7b-instruct-v0.2",
            "mistralai/mistral-7b-instruct-v0.3",
            "mistralai/mistral-large-3-675b-instruct-2512",
            "mistralai/mistral-medium-3-instruct",
            "mistralai/mistral-nemotron",
            "mistralai/mistral-small-24b-instruct",
            "mistralai/mistral-small-3.1-24b-instruct-2503",
            "mistralai/mixtral-8x7b-instruct-v0.1",
            "mistralai/mixtral-8x22b-instruct-v0.1",
            # --- Google ---
            "google/gemma-2-2b-it",
            "google/gemma-2-9b-it",
            "google/gemma-2-27b-it",
            "google/gemma-3-1b-it",
            "google/gemma-3-4b-it",
            "google/gemma-3-27b-it",
            "google/gemma-3n-e2b-it",
            "google/gemma-3n-e4b-it",
            "google/gemma-7b",
            "google/shieldgemma-9b",
            # --- NVIDIA ---
            "nvidia/llama-3.1-nemoguard-8b-content-safety",
            "nvidia/llama-3.1-nemoguard-8b-topic-control",
            "nvidia/llama-3.1-nemotron-70b-reward",
            "nvidia/llama-3.1-nemotron-nano-4b-v1.1",
            "nvidia/llama-3.1-nemotron-nano-8b-v1",
            "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
            "nvidia/llama-3.1-nemotron-safety-guard-8b-v3",
            "nvidia/llama-3.1-nemotron-ultra-253b-v1",
            "nvidia/llama-3.3-nemotron-super-49b-v1",
            "nvidia/llama-3.3-nemotron-super-49b-v1.5",
            "nvidia/llama3-chatqa-1.5-8b",
            "nvidia/nemotron-3-nano-30b-a3b",
            "nvidia/nemotron-4-mini-hindi-4b-instruct",
            "nvidia/nemotron-content-safety-reasoning-4b",
            "nvidia/nemotron-mini-4b-instruct",
            "nvidia/nemotron-nano-12b-v2-vl",
            "nvidia/nvidia-nemotron-nano-9b-v2",
            "nvidia/riva-translate-4b-instruct-v1.1",
            "nvidia/usdcode-llama-3.1-70b-instruct",
            # --- Deepseek ---
            "deepseek-ai/deepseek-r1-distill-llama-8b",
            "deepseek-ai/deepseek-r1-distill-qwen-14b",
            "deepseek-ai/deepseek-v3.1",
            "deepseek-ai/deepseek-v3.1-terminus",
            # --- Qwen ---
            "qwen/qwen2-7b-instruct",
            "qwen/qwen2.5-7b-instruct",
            "qwen/qwen2.5-coder-32b-instruct",
            "qwen/qwen2.5-coder-7b-instruct",
            "qwen/qwen3-235b-a22b",
            "qwen/qwen3-coder-480b-a35b-instruct",
            "qwen/qwen3-next-80b-a3b-instruct",
            "qwen/qwen3-next-80b-a3b-thinking",
            "qwen/qwq-32b",
            # --- Microsoft ---
            "microsoft/phi-3-medium-128k-instruct",
            "microsoft/phi-3-medium-4k-instruct",
            "microsoft/phi-3-mini-128k-instruct",
            "microsoft/phi-3-mini-4k-instruct",
            "microsoft/phi-3-small-128k-instruct",
            "microsoft/phi-3-small-8k-instruct",
            "microsoft/phi-3.5-mini-instruct",
            "microsoft/phi-3.5-vision-instruct",
            "microsoft/phi-4-mini-flash-reasoning",
            "microsoft/phi-4-multimodal-instruct",
            # --- Moonshot ---
            "moonshotai/kimi-k2-instruct-0905",
            # --- OpenAI (open-source) ---
            "openai/gpt-oss-20b",
            "openai/gpt-oss-120b",
            # --- MiniMax ---
            "minimaxai/minimax-m2",
            "minimaxai/minimax-m2.1",
            # --- AI21 Labs ---
            "ai21labs/jamba-1.5-mini-instruct",
            # --- Abacus AI ---
            "abacusai/dracarys-llama-3.1-70b-instruct",
            # --- IBM ---
            "ibm/granite-3.3-8b-instruct",
            "ibm/granite-guardian-3.0-8b",
            # --- Stepfun ---
            "stepfun-ai/step-3.5-flash",
            # --- Z-AI (Zhipu) ---
            "z-ai/glm4.7",
            # --- ByteDance ---
            "bytedance/seed-oss-36b-instruct",
            # --- Tiiuae ---
            "tiiuae/falcon3-7b-instruct",
            # --- Upstage ---
            "upstage/solar-10.7b-instruct",
            # --- Baichuan ---
            "baichuan-inc/baichuan2-13b-chat",
            # --- THU ---
            "thudm/chatglm3-6b",
            # --- Sarvamai ---
            "sarvamai/sarvam-m",
            # --- Rakuten ---
            "rakuten/rakutenai-7b-chat",
            "rakuten/rakutenai-7b-instruct",
            # --- Igenius ---
            "igenius/italia_10b_instruct_16k",
            # --- Stockmark ---
            "stockmark/stockmark-2-100b-instruct",
            # --- Speakleash ---
            "speakleash/bielik-11b-v2.3-instruct",
            "speakleash/bielik-11b-v2.6-instruct",
            # --- Other ---
            "gotocompany/gemma-2-9b-cpt-sahabatai-instruct",
            "institute-of-science-tokyo/llama-3.1-swallow-70b-instruct-v0.1",
            "institute-of-science-tokyo/llama-3.1-swallow-8b-instruct-v0.1",
            "marin/marin-8b-instruct",
            "mediatek/breeze-7b-instruct",
            "opengpt-x/teuken-7b-instruct-commercial-v0.4",
            "tokyotech-llm/llama-3-swallow-70b-instruct-v0.1",
            "utter-project/eurollm-9b-instruct",
            "yentinglin/llama-3-taiwan-70b-instruct",
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
