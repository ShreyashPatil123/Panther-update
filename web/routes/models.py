"""Models discovery — fetches live model lists from NVIDIA, Ollama, and Gemini."""
import asyncio
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from loguru import logger

router = APIRouter()


# ── Provider fetchers ──────────────────────────────────────────────────────

def _get_working_nvidia_models() -> set:
    """Return set of confirmed working NVIDIA NIM model IDs."""
    from src.api.nvidia_client import NVIDIAClient
    # Get the curated list without needing a real API key
    dummy = NVIDIAClient.__new__(NVIDIAClient)
    return set(dummy.get_available_models())


async def _fetch_nvidia_models(api_key: str, base_url: str) -> List[Dict[str, Any]]:
    """Fetch available models from NVIDIA NIM, filtered to confirmed working ones."""
    if not api_key or api_key == "your_api_key_here":
        return []
    working_set = _get_working_nvidia_models()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                models = []
                for m in data.get("data", []):
                    mid = m.get("id", "")
                    if not mid or mid not in working_set:
                        continue
                    models.append({
                        "id": mid,
                        "name": mid.split("/")[-1] if "/" in mid else mid,
                        "provider": "nvidia",
                        "label": "NVIDIA NIM",
                        "color": "#76b900",
                        "full_id": mid,
                    })
                return models
            logger.warning(f"NVIDIA /models returned {resp.status_code}")
    except Exception as e:
        logger.warning(f"NVIDIA model fetch failed: {e}")
    return []


async def _fetch_ollama_models(base_url: str, api_key: str = "") -> List[Dict[str, Any]]:
    """Fetch models from local or remote Ollama server (including Ollama Cloud)."""
    headers = {}
    if api_key and api_key != "ollama":
        headers["Authorization"] = f"Bearer {api_key}"

    ollama_root = base_url.rstrip("/").replace("/v1", "")
    is_cloud = "ollama.com" in base_url

    # Build list of (endpoint, parser) tuples to try
    attempts: list[tuple[str, str]] = []

    if is_cloud:
        # Ollama Cloud uses OpenAI-compat /v1/models
        attempts.append((f"{base_url.rstrip('/')}/models", "openai"))
    else:
        # Local Ollama uses /api/tags
        attempts.append((f"{ollama_root}/api/tags", "ollama"))
        attempts.append(("http://localhost:11434/api/tags", "ollama"))

    for endpoint, fmt in attempts:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(endpoint, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    models = []
                    if fmt == "openai":
                        # OpenAI-compat format: {"data": [{"id": ...}, ...]}
                        for m in data.get("data", []):
                            mid = m.get("id", "")
                            if not mid:
                                continue
                            models.append({
                                "id": mid,
                                "name": mid.split("/")[-1] if "/" in mid else mid,
                                "provider": "ollama",
                                "label": "Ollama Cloud" if is_cloud else "Ollama",
                                "color": "#a78bfa",
                                "full_id": mid,
                            })
                    else:
                        # Native Ollama format: {"models": [{"name": ...}, ...]}
                        for m in data.get("models", []):
                            name = m.get("name", "")
                            if not name:
                                continue
                            models.append({
                                "id": name,
                                "name": name,
                                "provider": "ollama",
                                "label": "Ollama",
                                "color": "#a78bfa",
                                "full_id": name,
                                "size": m.get("size", 0),
                            })
                    if models:
                        return models
                else:
                    logger.warning(f"Ollama {endpoint} returned {resp.status_code}")
        except Exception as e:
            logger.warning(f"Ollama fetch from {endpoint} failed: {e}")
            continue
    return []


_GEMINI_FREE_TIER_PREFIXES = (
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-3-flash",
)


async def _fetch_gemini_models(api_key: str) -> List[Dict[str, Any]]:
    """Fetch free-tier models from Google Gemini API."""
    if not api_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": api_key},
            )
            if resp.status_code == 200:
                data = resp.json()
                models = []
                for m in data.get("models", []):
                    name = m.get("name", "")  # e.g. "models/gemini-1.5-pro"
                    display = m.get("displayName", name)
                    mid = name.replace("models/", "")
                    # Only include models that support generateContent
                    supported = m.get("supportedGenerationMethods", [])
                    if "generateContent" not in supported:
                        continue
                    # Only keep free-tier models
                    if not mid.startswith(_GEMINI_FREE_TIER_PREFIXES):
                        continue
                    models.append({
                        "id": mid,
                        "name": display or mid,
                        "provider": "gemini",
                        "label": "Google Gemini",
                        "color": "#4285f4",
                        "full_id": mid,
                        "description": m.get("description", ""),
                    })
                return models
            logger.warning(f"Gemini /models returned {resp.status_code}")
    except Exception as e:
        logger.warning(f"Gemini model fetch failed: {e}")
    return []


def _fallback_nvidia_models() -> List[Dict[str, Any]]:
    """Return the curated hardcoded list when the API is unreachable."""
    hardcoded = [
        # Top picks — one from each family (verified 2026-02-23)
        "meta/llama-3.3-70b-instruct",
        "meta/llama-3.1-8b-instruct",
        "meta/llama-3.1-405b-instruct",
        "meta/llama-3.2-11b-vision-instruct",
        "mistralai/mistral-large-3-675b-instruct-2512",
        "mistralai/mistral-7b-instruct-v0.3",
        "mistralai/mixtral-8x22b-instruct-v0.1",
        "google/gemma-3-27b-it",
        "google/gemma-2-9b-it",
        "nvidia/llama-3.3-nemotron-super-49b-v1",
        "nvidia/llama-3.1-nemotron-nano-8b-v1",
        "deepseek-ai/deepseek-r1-distill-qwen-14b",
        "deepseek-ai/deepseek-v3.1",
        "qwen/qwen3-235b-a22b",
        "qwen/qwq-32b",
        "microsoft/phi-4-mini-flash-reasoning",
        "microsoft/phi-4-multimodal-instruct",
        "moonshotai/kimi-k2-instruct-0905",
    ]
    return [
        {
            "id": mid,
            "name": mid.split("/")[-1],
            "provider": "nvidia",
            "label": "NVIDIA NIM",
            "color": "#76b900",
            "full_id": mid,
            "fallback": True,
        }
        for mid in hardcoded
    ]


# ── Route ──────────────────────────────────────────────────────────────────

@router.get("/api/models")
async def list_all_models(request: Request):
    """Return all available models from all configured providers."""
    config = request.app.state.config

    nvidia_key = getattr(config, "nvidia_api_key", None) or ""
    google_key = getattr(config, "google_api_key", None) or ""
    ollama_enabled = getattr(config, "ollama_enabled", False)
    ollama_base_url = getattr(config, "ollama_base_url", "http://localhost:11434/v1") or ""
    ollama_api_key = getattr(config, "ollama_api_key", None) or ""

    # Fetch all providers concurrently
    tasks = []
    labels = []

    # NVIDIA — always try if key present; fall back to curated list
    tasks.append(_fetch_nvidia_models(nvidia_key, "https://integrate.api.nvidia.com/v1"))
    labels.append("nvidia")

    # Ollama — always try (even if not "enabled") so user can see what's local/cloud
    tasks.append(_fetch_ollama_models(ollama_base_url, ollama_api_key))
    labels.append("ollama")

    # Gemini
    tasks.append(_fetch_gemini_models(google_key))
    labels.append("gemini")

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_models: List[Dict] = []
    nvidia_live = False

    for label, result in zip(labels, results):
        if isinstance(result, Exception):
            logger.warning(f"Model fetch error for {label}: {result}")
            continue
        if label == "nvidia":
            if result:
                nvidia_live = True
                all_models.extend(result)
            # If NVIDIA key exists but API returned nothing, add fallback
            elif nvidia_key and nvidia_key != "your_api_key_here":
                all_models.extend(_fallback_nvidia_models())
        else:
            all_models.extend(result)

    # If no NVIDIA key at all and no other models — still show curated fallback
    if not all_models:
        all_models.extend(_fallback_nvidia_models())

    current_model = getattr(config, "default_model", "") or ""

    return JSONResponse({
        "models": all_models,
        "current_model": current_model,
        "nvidia_live": nvidia_live,
        "total": len(all_models),
    })


@router.post("/api/model/select")
async def select_model(request: Request):
    """Set the active model and re-init client if needed."""
    body = await request.json()
    model_id: str = body.get("model_id", "").strip()
    provider: str = body.get("provider", "nvidia")

    if not model_id:
        return JSONResponse({"ok": False, "error": "model_id required"}, status_code=400)

    config = request.app.state.config
    orchestrator = request.app.state.orchestrator

    if provider == "ollama":
        config.default_model = model_id
        config.ollama_enabled = True
        config.ollama_model = model_id
        api_key = getattr(config, "ollama_api_key", None) or "ollama"
        base_url = (config.ollama_base_url or "http://localhost:11434/v1").rstrip("/")
        orchestrator.set_api_key(api_key, base_url=base_url, provider="ollama")
        logger.info(f"Model selected (Ollama): {model_id}")

    elif provider == "gemini":
        google_key = getattr(config, "google_api_key", None) or ""
        if not google_key:
            return JSONResponse(
                {"ok": False, "error": "Google API key not configured. Add it in Settings first."},
                status_code=400,
            )
        config.default_model = model_id
        config.ollama_enabled = False
        config.gemini_model = model_id
        orchestrator.set_api_key(
            google_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            provider="gemini",
        )
        logger.info(f"Model selected (Gemini): {model_id}")

    else:  # nvidia / default
        nvidia_key = orchestrator._original_nvidia_key or config.nvidia_api_key or ""
        if not nvidia_key or nvidia_key == "your_api_key_here":
            return JSONResponse(
                {"ok": False, "error": "NVIDIA API key not configured. Add it in Settings first."},
                status_code=400,
            )
        config.default_model = model_id
        config.ollama_enabled = False
        orchestrator.set_api_key(nvidia_key, provider="nvidia")
        logger.info(f"Model selected (NVIDIA): {model_id}")

    return JSONResponse({"ok": True, "model": model_id, "provider": provider})
