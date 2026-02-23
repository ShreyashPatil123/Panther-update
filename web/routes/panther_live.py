"""Panther Live voice assistant routes."""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter()

STATIC_DIR = Path(__file__).parent.parent / "static"


@router.get("/panther-live")
async def serve_panther_live():
    """Serve the Panther Live voice assistant page."""
    return FileResponse(str(STATIC_DIR / "panther-live.html"))


@router.get("/api/google-key")
async def get_google_key(request: Request):
    """Return the Google API key for Gemini Live WebSocket."""
    config = request.app.state.config
    key = getattr(config, "google_api_key", None) or ""

    # Try secure storage if config doesn't have it
    if not key:
        try:
            from src.utils.secure_storage import get_google_api_key
            key = get_google_api_key() or ""
        except Exception:
            pass

    # Fallback to env
    if not key:
        import os
        key = os.environ.get("GOOGLE_API_KEY", "")

    return JSONResponse({"key": key})
