"""Settings/config routes."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel

router = APIRouter()


class SettingsUpdate(BaseModel):
    nvidia_api_key: str | None = None
    google_api_key: str | None = None
    ollama_api_key: str | None = None
    default_model: str | None = None
    ollama_enabled: bool | None = None
    ollama_base_url: str | None = None
    ollama_model: str | None = None


def _reinit_ollama_client(config, orchestrator):
    """Re-init the HTTP client for Ollama with current config (URL + optional bearer key)."""
    api_key = getattr(config, "ollama_api_key", None) or "ollama"  # 'ollama' = no-auth local
    base_url = (config.ollama_base_url or "http://localhost:11434/v1").rstrip("/")
    orchestrator.set_api_key(api_key, base_url=base_url)
    config.default_model = config.ollama_model
    logger.info(f"Ollama client re-inited: {base_url} / key={'set' if api_key != 'ollama' else 'none'}")


@router.get("/api/settings")
async def get_settings(request: Request):
    """Return current (non-secret) config."""
    config = request.app.state.config
    orchestrator = request.app.state.orchestrator

    from src.core.model_router import get_all_presets
    categories = []
    for cat, preset in get_all_presets().items():
        short_model = preset.model.split("/")[-1] if "/" in preset.model else preset.model
        categories.append({
            "id": cat.value,
            "icon": preset.emoji,
            "label": preset.label,
            "desc": preset.description,
            "model": short_model,
        })

    return JSONResponse({
        "default_model": config.default_model,
        "ollama_enabled": config.ollama_enabled,
        "ollama_base_url": config.ollama_base_url,
        "ollama_model": config.ollama_model,
        "has_nvidia_key": bool(config.nvidia_api_key and config.nvidia_api_key != "your_api_key_here"),
        "has_google_key": bool(getattr(config, "google_api_key", None)),
        "has_ollama_key": bool(getattr(config, "ollama_api_key", None)),
        "is_ready": orchestrator.is_ready,
        "categories": categories,
    })


@router.post("/api/settings")
async def update_settings(body: SettingsUpdate, request: Request):
    """Apply new settings at runtime."""
    config = request.app.state.config
    orchestrator = request.app.state.orchestrator

    try:
        ollama_changed = False  # track whether any Ollama param actually changed

        # ── NVIDIA API key ──────────────────────────────────────────────────
        if body.nvidia_api_key is not None and body.nvidia_api_key.strip():
            key = body.nvidia_api_key.strip()
            config.nvidia_api_key = key
            if not config.ollama_enabled:
                orchestrator.set_api_key(key)  # reinit HTTP client immediately
            try:
                from src.utils.secure_storage import store_api_key
                store_api_key(key)
            except Exception:
                pass
            logger.info("NVIDIA API key updated")

        # ── Google API key ───────────────────────────────────────────────────
        if body.google_api_key is not None and body.google_api_key.strip():
            key = body.google_api_key.strip()
            config.google_api_key = key
            try:
                from src.utils.secure_storage import store_google_api_key
                store_google_api_key(key)
            except Exception:
                pass
            logger.info("Google API key updated")

        # ── Ollama API key ───────────────────────────────────────────────────
        if body.ollama_api_key is not None and body.ollama_api_key.strip():
            key = body.ollama_api_key.strip()
            try:
                config.ollama_api_key = key
            except Exception:
                object.__setattr__(config, "ollama_api_key", key)
            ollama_changed = True
            logger.info("Ollama API key updated")

        # ── Ollama toggle ────────────────────────────────────────────────────
        if body.ollama_enabled is not None:
            config.ollama_enabled = body.ollama_enabled
            ollama_changed = True

        # ── Ollama base URL ──────────────────────────────────────────────────
        if body.ollama_base_url is not None:
            config.ollama_base_url = body.ollama_base_url.strip() or "http://localhost:11434/v1"
            ollama_changed = True

        # ── Ollama model ─────────────────────────────────────────────────────
        if body.ollama_model is not None:
            config.ollama_model = body.ollama_model.strip()
            ollama_changed = True

        # ── Default model (NVIDIA mode) ──────────────────────────────────────
        if body.default_model is not None and body.default_model.strip():
            if not config.ollama_enabled:
                config.default_model = body.default_model.strip()

        # ── Re-init client if Ollama settings changed ────────────────────────
        if ollama_changed:
            if config.ollama_enabled:
                _reinit_ollama_client(config, orchestrator)
            else:
                # Switched FROM Ollama → back to NVIDIA
                nvidia_key = config.nvidia_api_key
                if nvidia_key and nvidia_key != "your_api_key_here":
                    orchestrator.set_api_key(nvidia_key)
                    logger.info("Switched back to NVIDIA client")

        return JSONResponse({"ok": True})

    except Exception as e:
        logger.error(f"Settings update failed: {e}")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
