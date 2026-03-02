"""File processor — converts images, documents and videos into API-ready content.

Supports:
  - Images (.jpg, .png, .gif, .webp, .bmp) → base64 data URI for vision models
  - Documents (.pdf, .txt, .md, .docx, .csv, .json, .py, etc.) → extracted text
  - Videos (.mp4, .avi, .mov, .mkv) → key frame extraction → base64 images
"""

import base64
import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

# ── File-type classifications ────────────────────────────────────────────────

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv"}
TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml",
    ".py", ".js", ".ts", ".java", ".cpp", ".c", ".h", ".cs", ".go",
    ".rs", ".rb", ".php", ".html", ".css", ".sql", ".sh", ".bat",
    ".ps1", ".env", ".ini", ".cfg", ".toml", ".log",
}
DOCUMENT_EXTENSIONS = {".pdf", ".docx"}

# Vision-capable models on NVIDIA NIM
VISION_MODELS = [
    "meta/llama-3.2-90b-vision-instruct",
    "meta/llama-3.2-11b-vision-instruct",
    "meta/llama-4-maverick-17b-128e-instruct",
    "meta/llama-4-scout-17b-16e-instruct",
    "microsoft/phi-3.5-vision-instruct",
    "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
]

DEFAULT_VISION_MODEL = "moonshotai/kimi-k2.5"
MAX_IMAGE_DIMENSION = 512   # Resize images larger than this (keeps base64 small)
MAX_VIDEO_FRAMES = 2        # Number of key frames to extract from videos
MAX_TEXT_CHARS = 30000      # Truncate very long documents


class FileType:
    """Enum-like constants for file types."""
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"
    TEXT = "text"
    UNKNOWN = "unknown"


def classify_file(filepath: str) -> str:
    """Classify a file by its extension."""
    ext = Path(filepath).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return FileType.IMAGE
    elif ext in VIDEO_EXTENSIONS:
        return FileType.VIDEO
    elif ext in DOCUMENT_EXTENSIONS:
        return FileType.DOCUMENT
    elif ext in TEXT_EXTENSIONS:
        return FileType.TEXT
    else:
        return FileType.UNKNOWN


def get_mime_type(filepath: str) -> str:
    """Get MIME type for a file."""
    mime, _ = mimetypes.guess_type(filepath)
    return mime or "application/octet-stream"


# ── Image Processing ─────────────────────────────────────────────────────────

def _resize_image_if_needed(img) -> "Image":
    """Resize image if it exceeds MAX_IMAGE_DIMENSION."""
    from PIL import Image
    w, h = img.size
    if max(w, h) > MAX_IMAGE_DIMENSION:
        ratio = MAX_IMAGE_DIMENSION / max(w, h)
        new_size = (int(w * ratio), int(h * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        logger.debug(f"Resized image from {w}x{h} to {new_size[0]}x{new_size[1]}")
    return img


def process_image(filepath: str) -> Dict[str, Any]:
    """Convert an image file to a base64 data URI content block.
    
    Returns:
        OpenAI-compatible content block: {"type": "image_url", "image_url": {"url": "data:..."}}
    """
    from PIL import Image
    import io

    logger.info(f"Processing image: {filepath}")
    img = Image.open(filepath)

    # Convert to RGB if necessary (e.g., RGBA, P mode)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    img = _resize_image_if_needed(img)

    # Encode to base64 — use moderate quality to keep payload small
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=75)
    b64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return {
        "type": "image_url",
        "image_url": {
            "url": f"data:image/jpeg;base64,{b64_data}"
        }
    }


# ── Document Processing ──────────────────────────────────────────────────────

def _extract_pdf_text(filepath: str) -> str:
    """Extract text from a PDF file."""
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(filepath)
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                pages.append(f"--- Page {i + 1} ---\n{text}")
        return "\n\n".join(pages)
    except Exception as e:
        logger.error(f"Error extracting PDF text: {e}")
        return f"[Error reading PDF: {e}]"


def _extract_docx_text(filepath: str) -> str:
    """Extract text from a DOCX file."""
    try:
        from docx import Document
        doc = Document(filepath)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except Exception as e:
        logger.error(f"Error extracting DOCX text: {e}")
        return f"[Error reading DOCX: {e}]"


def process_document(filepath: str) -> str:
    """Extract text content from a document file.
    
    Returns:
        Extracted text string.
    """
    ext = Path(filepath).suffix.lower()
    logger.info(f"Processing document: {filepath} (type: {ext})")

    if ext == ".pdf":
        text = _extract_pdf_text(filepath)
    elif ext == ".docx":
        text = _extract_docx_text(filepath)
    else:
        text = f"[Unsupported document format: {ext}]"

    # Truncate if too long
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + f"\n\n[... truncated at {MAX_TEXT_CHARS} characters]"

    return text


def process_text_file(filepath: str) -> str:
    """Read a text-based file and return its content.
    
    Returns:
        File content as string.
    """
    logger.info(f"Processing text file: {filepath}")
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception as e:
        logger.error(f"Error reading text file: {e}")
        return f"[Error reading file: {e}]"

    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + f"\n\n[... truncated at {MAX_TEXT_CHARS} characters]"

    return text


# ── Video Processing ─────────────────────────────────────────────────────────

def process_video(filepath: str, max_frames: int = MAX_VIDEO_FRAMES) -> List[Dict[str, Any]]:
    """Extract key frames from a video and return as image content blocks.
    
    Returns:
        List of OpenAI-compatible image_url content blocks.
    """
    import cv2
    from PIL import Image
    import io

    logger.info(f"Processing video: {filepath} (extracting {max_frames} frames)")

    cap = cv2.VideoCapture(filepath)
    if not cap.isOpened():
        logger.error(f"Cannot open video: {filepath}")
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        cap.release()
        return []

    # Sample evenly spaced frames
    frame_indices = [int(i * total_frames / max_frames) for i in range(max_frames)]
    
    content_blocks = []
    for idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            continue

        # Convert BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)
        img = _resize_image_if_needed(img)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=60)
        b64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")

        content_blocks.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{b64_data}"
            }
        })

    cap.release()
    logger.info(f"Extracted {len(content_blocks)} frames from video")
    return content_blocks


# ── Main Entry Point ─────────────────────────────────────────────────────────

def build_multimodal_content(
    user_message: str,
    attachments: List[str],
) -> Tuple[List[Dict[str, Any]], bool, Optional[str]]:
    """Build multimodal content blocks from user message + attachments.
    
    Args:
        user_message: The user's text message.
        attachments: List of file paths.
    
    Returns:
        Tuple of:
         - content: List of content blocks (for the user message)
         - needs_vision: Whether a vision model is required
         - context_text: Any document/text content to prepend as context (or None)
    """
    content_blocks: List[Dict[str, Any]] = []
    text_context_parts: List[str] = []
    needs_vision = False

    for filepath in attachments:
        file_type = classify_file(filepath)
        filename = os.path.basename(filepath)

        if file_type == FileType.IMAGE:
            needs_vision = True
            try:
                img_block = process_image(filepath)
                content_blocks.append(img_block)
                logger.info(f"Added image: {filename}")
            except Exception as e:
                logger.error(f"Failed to process image {filename}: {e}")
                text_context_parts.append(f"[Failed to load image: {filename} — {e}]")

        elif file_type == FileType.VIDEO:
            needs_vision = True
            try:
                frame_blocks = process_video(filepath)
                content_blocks.extend(frame_blocks)
                text_context_parts.append(
                    f"[Video: {filename} — {len(frame_blocks)} key frames extracted for analysis]"
                )
            except Exception as e:
                logger.error(f"Failed to process video {filename}: {e}")
                text_context_parts.append(f"[Failed to load video: {filename} — {e}]")

        elif file_type == FileType.DOCUMENT:
            try:
                doc_text = process_document(filepath)
                text_context_parts.append(
                    f"📄 **Document: {filename}**\n\n{doc_text}"
                )
            except Exception as e:
                logger.error(f"Failed to process document {filename}: {e}")
                text_context_parts.append(f"[Failed to read document: {filename} — {e}]")

        elif file_type == FileType.TEXT:
            try:
                file_text = process_text_file(filepath)
                ext = Path(filepath).suffix.lstrip(".")
                text_context_parts.append(
                    f"📄 **File: {filename}**\n```{ext}\n{file_text}\n```"
                )
            except Exception as e:
                logger.error(f"Failed to read text file {filename}: {e}")
                text_context_parts.append(f"[Failed to read file: {filename} — {e}]")

        else:
            text_context_parts.append(f"[Unsupported file type: {filename}]")

    # Build the context text
    context_text = "\n\n".join(text_context_parts) if text_context_parts else None

    return content_blocks, needs_vision, context_text
