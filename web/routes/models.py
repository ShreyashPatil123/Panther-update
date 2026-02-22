"""Models discovery — fetches live model lists from NVIDIA, Ollama, and Gemini."""
import asyncio
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from loguru import logger

router = APIRouter()


# ── Provider fetchers ──────────────────────────────────────────────────────

async def _fetch_nvidia_models(api_key: str, base_url: str) -> List[Dict[str, Any]]:
    """Fetch available models from NVIDIA NIM (or any OpenAI-compat API)."""
    if not api_key or api_key == "your_api_key_here":
        return []
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
                    if not mid:
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


async def _fetch_ollama_models(base_url: str) -> List[Dict[str, Any]]:
    """Fetch models from local or remote Ollama server."""
    # Ollama API endpoint is /api/tags (not /v1/models)
    ollama_root = base_url.rstrip("/").replace("/v1", "")
    endpoints = [
        f"{ollama_root}/api/tags",
        "http://localhost:11434/api/tags",
    ]
    for endpoint in endpoints:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(endpoint)
                if resp.status_code == 200:
                    data = resp.json()
                    models = []
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
        except Exception:
            continue
    return []


async def _fetch_gemini_models(api_key: str) -> List[Dict[str, Any]]:
    """Fetch models from Google Gemini API."""
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
        # Top picks — one from each family
        "meta/llama-3.3-70b-instruct",
        "meta/llama-3.1-8b-instruct",
        "meta/llama-3.1-405b-instruct",
        "meta/llama-3.2-11b-vision-instruct",
        "mistralai/mistral-large-3-675b-instruct-2512",
        "mistralai/mistral-7b-instruct-v0.3",
        "mistralai/mixtral-8x22b-instruct-v0.1",
        "google/gemma-3-27b-it",
        "google/gemma-3-12b-it",
        "nvidia/llama-3.3-nemotron-super-49b-v1",
        "nvidia/llama-3.1-nemotron-nano-8b-v1",
        "deepseek-ai/deepseek-r1-distill-qwen-32b",
        "deepseek-ai/deepseek-v3.2",
        "qwen/qwen3-235b-a22b",
        "qwen/qwq-32b",
        "microsoft/phi-4-mini-instruct",
        "microsoft/phi-4-multimodal-instruct",
        "moonshotai/kimi-k2-instruct",
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

    # Fetch all providers concurrently
    tasks = []
    labels = []

    # NVIDIA — always try if key present; fall back to curated list
    tasks.append(_fetch_nvidia_models(nvidia_key, "https://integrate.api.nvidia.com/v1"))
    labels.append("nvidia")

    # Ollama — always try (even if not "enabled") so user can see what's local
    tasks.append(_fetch_ollama_models(ollama_base_url))
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

    config.default_model = model_id

    if provider == "ollama":
        config.ollama_enabled = True
        config.ollama_model = model_id
        api_key = getattr(config, "ollama_api_key", None) or "ollama"
        base_url = (config.ollama_base_url or "http://localhost:11434/v1").rstrip("/")
        orchestrator.set_api_key(api_key, base_url=base_url)
        logger.info(f"Model selected (Ollama): {model_id}")

    elif provider == "gemini":
        # Gemini uses a separate client path — set flag on config
        config.ollama_enabled = False
        config.gemini_model = model_id
        # For now route via NVIDIA client with google key as bearer
        # (real Gemini integration would need genai SDK — placeholder)
        google_key = getattr(config, "google_api_key", None) or ""
        if google_key:
            orchestrator.set_api_key(
                google_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            )
        logger.info(f"Model selected (Gemini): {model_id}")

    else:  # nvidia / default
        config.ollama_enabled = False
        nvidia_key = config.nvidia_api_key or ""
        if nvidia_key and nvidia_key != "your_api_key_here":
            orchestrator.set_api_key(nvidia_key)
        logger.info(f"Model selected (NVIDIA): {model_id}")

    return JSONResponse({"ok": True, "model": model_id, "provider": provider})
