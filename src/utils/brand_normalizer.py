"""
Universal Brand Name Normalizer
================================
Fixes typos, spacing issues, and misspellings in brand/website names
BEFORE they enter the URL resolution pipeline.

3-Layer approach:
  Layer 1 — Fast heuristics (instant, no deps)
  Layer 2 — rapidfuzz vs SITE_MAP keys (<1ms)
  Layer 3 — Gemini LLM (universal, ~1s)
"""

import re
from typing import Optional
from loguru import logger

# ── Layer 2 dependency ────────────────────────────────────────────────────────
try:
    from rapidfuzz import fuzz, process as rf_process
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False
    logger.warning("[Normalizer] rapidfuzz not installed — Layer 2 disabled")


# ═══════════════════════════════════════════════════════════════════════════════
#  Layer 1 — Fast Heuristics (spacing, case, possessives)
# ═══════════════════════════════════════════════════════════════════════════════

def _heuristic_clean(brand: str) -> str:
    """Basic cleaning — runs in <0.1ms."""
    # Lowercase + strip
    cleaned = brand.strip().lower()
    # Remove possessives
    cleaned = re.sub(r"['']s$", "", cleaned)
    # Remove trailing punctuation
    cleaned = cleaned.rstrip(".,!?;:")
    # Collapse multiple spaces to single
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _try_space_collapse(brand: str) -> str:
    """
    Try collapsing spaces to see if it forms a known-looking word.
    'you tube' → 'youtube', 'face book' → 'facebook'
    Returns the collapsed version only if the original had spaces.
    """
    if " " not in brand:
        return brand
    return brand.replace(" ", "")


# ═══════════════════════════════════════════════════════════════════════════════
#  Layer 2 — rapidfuzz vs SITE_MAP (known sites, <1ms)
# ═══════════════════════════════════════════════════════════════════════════════

def _fuzzy_match_known_sites(brand: str, score_cutoff: int = 80) -> Optional[str]:
    """
    Fuzzy match against SITE_MAP keys.
    Uses token_sort_ratio for word-order independence.
    Returns the matched site name or None.
    """
    if not HAS_RAPIDFUZZ:
        return None

    try:
        from src.capabilities.desktop_browser_agent import SITE_MAP
        known_sites = list(SITE_MAP.keys())
    except ImportError:
        return None

    if not known_sites:
        return None

    # Also try the space-collapsed version
    candidates_to_try = [brand]
    collapsed = _try_space_collapse(brand)
    if collapsed != brand:
        candidates_to_try.append(collapsed)

    for candidate in candidates_to_try:
        result = rf_process.extractOne(
            candidate,
            known_sites,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=score_cutoff,
        )
        if result:
            matched_name, score, _idx = result
            logger.info(f"[Normalizer] L2 fuzzy match: '{brand}' → '{matched_name}' (score={score})")
            return matched_name

    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Layer 3 — Gemini LLM (universal, ~1s)
# ═══════════════════════════════════════════════════════════════════════════════

async def _gemini_normalize(brand: str, gemini_model) -> Optional[str]:
    """
    Ask Gemini to correct the brand name.
    Only called if Layer 1+2 didn't fix the typo.
    """
    if not gemini_model:
        return None

    prompt = (
        "The user typed a brand or website name with possible typos or spacing issues. "
        "Return ONLY the corrected brand/website name — nothing else, no explanation, "
        "no quotes, no punctuation. If the name is already correct, return it as-is.\n\n"
        f"Input: {brand}"
    )

    try:
        resp = await gemini_model.generate_content_async(prompt)
        corrected = resp.text.strip().strip("\"'`").strip()
        # Basic sanity: result should be short and look like a brand name
        if corrected and len(corrected) < 60 and not corrected.startswith("http"):
            corrected_lower = corrected.lower()
            if corrected_lower != brand:
                logger.info(f"[Normalizer] L3 Gemini corrected: '{brand}' → '{corrected_lower}'")
            return corrected_lower
        return brand
    except Exception as e:
        logger.warning(f"[Normalizer] L3 Gemini failed: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

async def normalize_brand(raw: str, gemini_model=None) -> str:
    """
    Universal brand normalizer. Fixes typos and spacing in brand names.

    Args:
        raw:          Raw brand name from user input (e.g., "youtueb", "net flix")
        gemini_model: Optional Gemini model for Layer 3 LLM correction

    Returns:
        Normalized brand name (e.g., "youtube", "netflix")

    Examples:
        >>> await normalize_brand("youtueb")   → "youtube"
        >>> await normalize_brand("net flix")   → "netflix"
        >>> await normalize_brand("amzon")     → "amazon"
        >>> await normalize_brand("zara")      → "zara"  (correct, passes through)
    """
    if not raw or len(raw) < 2:
        return raw

    # ── Layer 1: Fast heuristic clean ─────────────────────────────────────
    cleaned = _heuristic_clean(raw)
    logger.debug(f"[Normalizer] L1 heuristic: '{raw}' → '{cleaned}'")

    # If the cleaned version is empty, return original
    if not cleaned:
        return raw

    # ── Layer 2: rapidfuzz vs SITE_MAP ────────────────────────────────────
    fuzzy_match = _fuzzy_match_known_sites(cleaned)
    if fuzzy_match:
        return fuzzy_match

    # Also try space-collapsed version against SITE_MAP
    collapsed = _try_space_collapse(cleaned)
    if collapsed != cleaned:
        fuzzy_collapsed = _fuzzy_match_known_sites(collapsed)
        if fuzzy_collapsed:
            return fuzzy_collapsed

    # ── Layer 3: Gemini LLM (universal fallback) ──────────────────────────
    # Only invoke if the brand looks potentially misspelled:
    # - Short names (< 15 chars) are more likely brands
    # - Names without dots (not already a domain)
    if gemini_model and "." not in cleaned and len(cleaned) < 30:
        gemini_result = await _gemini_normalize(cleaned, gemini_model)
        if gemini_result:
            return gemini_result

    # If all layers pass through, return the heuristic-cleaned version
    return cleaned
