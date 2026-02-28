"""Finance Engine — Real-time financial data via Twelve Data API.

Provides structured, accurate market quotes for stocks, crypto, forex,
commodities, and metals. Uses a hybrid ticker resolver (hardcoded map +
LLM fallback), 60-second in-memory cache, rate limiting, and India-
specific gold conversion logic.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# ── Twelve Data configuration ────────────────────────────────────────────────
TWELVE_DATA_API_KEY = ""
TWELVE_DATA_BASE   = "https://api.twelvedata.com"

# ── Rate-limit constants (free plan) ─────────────────────────────────────────
MAX_REQUESTS_PER_MINUTE = 8
MAX_REQUESTS_PER_DAY    = 800

# ── Cache TTL ────────────────────────────────────────────────────────────────
CACHE_TTL_SECONDS = 60

# ── Gold conversion constants ────────────────────────────────────────────────
TROY_OUNCE_TO_GRAMS = 31.1035
KARAT_24_FACTOR     = 1.0
KARAT_22_FACTOR     = 22.0 / 24.0
KARAT_18_FACTOR     = 18.0 / 24.0


# ══════════════════════════════════════════════════════════════════════════════
#  Hardcoded Symbol Map  (Fix #1 — hybrid resolver, LLM is fallback only)
# ══════════════════════════════════════════════════════════════════════════════

SYMBOL_MAP: Dict[str, str] = {
    # ── Stocks (US) ───────────────────────────────────────────────────
    "apple":        "AAPL",
    "microsoft":    "MSFT",
    "google":       "GOOGL",
    "alphabet":     "GOOGL",
    "amazon":       "AMZN",
    "tesla":        "TSLA",
    "nvidia":       "NVDA",
    "meta":         "META",
    "facebook":     "META",
    "netflix":      "NFLX",
    "amd":          "AMD",
    "intel":        "INTC",
    "ibm":          "IBM",
    "disney":       "DIS",
    "walmart":      "WMT",
    "jpmorgan":     "JPM",
    "visa":         "V",
    "mastercard":   "MA",
    "paypal":       "PYPL",
    "uber":         "UBER",
    "airbnb":       "ABNB",
    "snap":         "SNAP",
    "snapchat":     "SNAP",
    "spotify":      "SPOT",
    "adobe":        "ADBE",
    "salesforce":   "CRM",
    "oracle":       "ORCL",
    "cisco":        "CSCO",
    "boeing":       "BA",
    "coca cola":    "KO",
    "pepsi":        "PEP",
    "mcdonalds":    "MCD",
    "nike":         "NKE",
    "starbucks":    "SBUX",
    "twitter":      "TWTR",
    "x corp":       "TWTR",

    # ── Stocks (India – NSE) ──────────────────────────────────────────
    "reliance":     "RELIANCE:NSE",
    "tcs":          "TCS:NSE",
    "infosys":      "INFY:NSE",
    "wipro":        "WIPRO:NSE",
    "hdfc":         "HDFCBANK:NSE",
    "hdfc bank":    "HDFCBANK:NSE",
    "icici":        "ICICIBANK:NSE",
    "icici bank":   "ICICIBANK:NSE",
    "sbi":          "SBIN:NSE",
    "bajaj finance":"BAJFINANCE:NSE",
    "kotak":        "KOTAKBANK:NSE",
    "kotak bank":   "KOTAKBANK:NSE",
    "maruti":       "MARUTI:NSE",
    "tatamotors":   "TATAMOTORS:NSE",
    "tata motors":  "TATAMOTORS:NSE",
    "tata steel":   "TATASTEEL:NSE",
    "asian paints":  "ASIANPAINT:NSE",
    "hul":          "HINDUNILVR:NSE",
    "hindustan unilever": "HINDUNILVR:NSE",
    "itc":          "ITC:NSE",
    "adani":        "ADANIENT:NSE",
    "l&t":          "LT:NSE",
    "larsen":       "LT:NSE",
    "sun pharma":   "SUNPHARMA:NSE",
    "axis bank":    "AXISBANK:NSE",
    "bharti airtel": "BHARTIARTL:NSE",
    "airtel":       "BHARTIARTL:NSE",
    "tech mahindra": "TECHM:NSE",
    "mahindra":     "M&M:NSE",
    "power grid":   "POWERGRID:NSE",
    "ntpc":         "NTPC:NSE",
    "ultratech":    "ULTRACEMCO:NSE",
    "titan":        "TITAN:NSE",
    "bajaj auto":   "BAJAJ-AUTO:NSE",

    # ── Indices ───────────────────────────────────────────────────────
    "nifty":        "NIFTY 50:NSE",
    "nifty 50":     "NIFTY 50:NSE",
    "sensex":       "SENSEX:BSE",
    "bse sensex":   "SENSEX:BSE",
    "dow jones":    "DJI",
    "dow":          "DJI",
    "s&p 500":      "SPX",
    "s&p":          "SPX",
    "nasdaq":       "IXIC",
    "ftse":         "FTSE:LSE",
    "dax":          "DAX:XETRA",
    "nikkei":       "NI225",
    "hang seng":    "HSI",

    # ── Crypto ────────────────────────────────────────────────────────
    "bitcoin":      "BTC/USD",
    "btc":          "BTC/USD",
    "ethereum":     "ETH/USD",
    "eth":          "ETH/USD",
    "solana":       "SOL/USD",
    "sol":          "SOL/USD",
    "dogecoin":     "DOGE/USD",
    "doge":         "DOGE/USD",
    "xrp":          "XRP/USD",
    "ripple":       "XRP/USD",
    "cardano":      "ADA/USD",
    "ada":          "ADA/USD",
    "polkadot":     "DOT/USD",
    "dot":          "DOT/USD",
    "litecoin":     "LTC/USD",
    "ltc":          "LTC/USD",
    "avalanche":    "AVAX/USD",
    "avax":         "AVAX/USD",
    "chainlink":    "LINK/USD",
    "link":         "LINK/USD",
    "shiba inu":    "SHIB/USD",
    "shib":         "SHIB/USD",
    "bnb":          "BNB/USD",
    "binance":      "BNB/USD",
    "polygon":      "MATIC/USD",
    "matic":        "MATIC/USD",

    # ── Forex ─────────────────────────────────────────────────────────
    "dollar":       "USD/INR",
    "usd inr":      "USD/INR",
    "dollar rupee": "USD/INR",
    "euro":         "EUR/USD",
    "eur usd":      "EUR/USD",
    "pound":        "GBP/USD",
    "gbp usd":      "GBP/USD",
    "yen":          "USD/JPY",
    "usd jpy":      "USD/JPY",

    # ── Commodities / Metals ──────────────────────────────────────────
    "gold":         "XAU/USD",
    "silver":       "XAG/USD",
    "platinum":     "XPT/USD",
    "palladium":    "XPD/USD",
    "crude oil":    "CL",
    "oil":          "CL",
    "brent":        "BRN",
    "natural gas":  "NG",
}


# ══════════════════════════════════════════════════════════════════════════════
#  Data classes
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class FinanceQuote:
    """Lean quote — only the fields that matter (Fix #5)."""
    symbol: str
    name: str
    exchange: str
    price: str
    change: str
    percent_change: str
    currency: str = "USD"
    is_market_open: bool = False
    fifty_two_week_low: str = ""
    fifty_two_week_high: str = ""


@dataclass
class _CacheEntry:
    """In-memory cache entry (Fix #2)."""
    quote: FinanceQuote
    timestamp: float


# ══════════════════════════════════════════════════════════════════════════════
#  Finance Engine
# ══════════════════════════════════════════════════════════════════════════════

class FinanceEngine:
    """Twelve Data-powered finance capability for PANTHER."""

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=15.0,
            headers={"User-Agent": "PANTHER-Agent/1.0"},
            follow_redirects=True,
        )
        # ── Cache (Fix #2) ────────────────────────────────────────────
        self._cache: Dict[str, _CacheEntry] = {}

        # ── Rate limiter (Fix #4) ─────────────────────────────────────
        self._minute_window: List[float] = []
        self._day_count = 0
        self._day_reset: float = time.time() + 86400

    async def close(self):
        await self.client.aclose()

    # ──────────────────────────────────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────────────────────────────────

    async def get_quote(
        self,
        user_query: str,
        nvidia_client=None,
        model: str = "",
    ) -> Tuple[Optional[FinanceQuote], str]:
        """
        End-to-end: resolve ticker → cache check → API call → return quote.

        Returns:
            (FinanceQuote | None, synthesized_text)
        """
        # 1. Resolve ticker
        symbol = await self.resolve_symbol(user_query, nvidia_client, model)
        if not symbol:
            return None, f"Sorry, I couldn't identify a financial instrument in your query."

        logger.info(f"Resolved ticker: '{symbol}' from query: '{user_query[:60]}'")

        # 2. Check cache (Fix #2)
        cached = self._get_cached(symbol)
        if cached:
            logger.info(f"Cache hit for {symbol}")
            quote = cached
        else:
            # 3. Rate-limit check (Fix #4)
            if not self._can_request():
                return None, (
                    "⚠️ Rate limit reached for market data API. "
                    "Please wait a moment before asking again."
                )

            # 4. Fetch from Twelve Data (with retry)
            quote = await self._fetch_quote(symbol)
            if not quote:
                return None, (
                    f"Could not fetch data for **{symbol}**. "
                    f"The market may be closed or the symbol may be unavailable."
                )
            self._set_cached(symbol, quote)

        # 5. India gold conversion (Fix #3)
        india_gold_text = ""
        wants_india = self._wants_india_gold(user_query, symbol)
        if wants_india:
            india_gold_text = await self._convert_gold_to_inr(quote)

        # 6. Synthesize response
        text = self._format_quote(quote, india_gold_text)

        return quote, text

    # ──────────────────────────────────────────────────────────────────────
    #  Hybrid Ticker Resolver (Fix #1)
    # ──────────────────────────────────────────────────────────────────────

    async def resolve_symbol(
        self,
        user_query: str,
        nvidia_client=None,
        model: str = "",
    ) -> Optional[str]:
        """Resolve a natural-language query to a Twelve Data ticker symbol.

        Strategy:
          1. Check hardcoded SYMBOL_MAP first (instant, reliable).
             Uses word-boundary regex to avoid false substring matches
             (e.g., 'itc' in 'price'). Longer keys are checked first
             so 'tata motors' matches before 'tata'.
          2. Fall back to LLM extraction (handles obscure tickers).
        """
        import re as _re
        query_lower = user_query.lower()

        # ── Pass 1: word-boundary match in symbol map ─────────────────
        # Sort keys longest-first so multi-word keys get priority
        sorted_keys = sorted(SYMBOL_MAP.keys(), key=len, reverse=True)
        for key in sorted_keys:
            # Build a word-boundary pattern for this key
            pattern = r'\b' + _re.escape(key) + r'\b'
            if _re.search(pattern, query_lower):
                return SYMBOL_MAP[key]

        # ── Pass 2: LLM fallback ──────────────────────────────────────
        if nvidia_client:
            try:
                return await self._llm_extract_symbol(user_query, nvidia_client, model)
            except Exception as e:
                logger.warning(f"LLM symbol extraction failed: {e}")

        return None

    async def _llm_extract_symbol(
        self, query: str, nvidia_client, model: str
    ) -> Optional[str]:
        """Ask the LLM to extract the Twelve Data ticker symbol."""
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a financial ticker resolver. Given a user query, extract the "
                    "exact Twelve Data API symbol.\n\n"
                    "Rules:\n"
                    "- US stocks: uppercase ticker (e.g., AAPL, TSLA)\n"
                    "- Indian stocks: SYMBOL:NSE or SYMBOL:BSE (e.g., RELIANCE:NSE)\n"
                    "- Crypto: COIN/USD (e.g., BTC/USD, ETH/USD)\n"
                    "- Forex: BASE/QUOTE (e.g., EUR/USD, USD/INR)\n"
                    "- Gold: XAU/USD, Silver: XAG/USD\n"
                    "- Indices: use Twelve Data format (e.g., NIFTY 50:NSE, SPX, DJI)\n\n"
                    "Respond with ONLY the symbol, nothing else. "
                    "If you cannot identify a symbol, respond with 'UNKNOWN'."
                ),
            },
            {"role": "user", "content": query},
        ]

        result = ""
        async for chunk in nvidia_client.chat_completion(
            messages, model=model, stream=False, max_tokens=16, temperature=0.0
        ):
            result += chunk

        symbol = result.strip().upper()
        if symbol and symbol != "UNKNOWN":
            return symbol
        return None

    # ──────────────────────────────────────────────────────────────────────
    #  Twelve Data API Call (with retry)
    # ──────────────────────────────────────────────────────────────────────

    async def _fetch_quote(self, symbol: str, retries: int = 2) -> Optional[FinanceQuote]:
        """Fetch a quote from Twelve Data with retry logic."""
        url = f"{TWELVE_DATA_BASE}/quote"
        params = {"symbol": symbol, "apikey": TWELVE_DATA_API_KEY}

        for attempt in range(retries + 1):
            try:
                resp = await self.client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

                # Check for API error
                if data.get("code") or data.get("status") == "error":
                    logger.warning(f"Twelve Data error for {symbol}: {data.get('message', data)}")
                    return None

                self._record_request()

                # ── Extract only the lean fields (Fix #5) ─────────────
                ftw = data.get("fifty_two_week", {})
                return FinanceQuote(
                    symbol=data.get("symbol", symbol),
                    name=data.get("name", symbol),
                    exchange=data.get("exchange", ""),
                    price=data.get("close", data.get("price", "N/A")),
                    change=data.get("change", "0"),
                    percent_change=data.get("percent_change", "0"),
                    currency=data.get("currency", "USD"),
                    is_market_open=data.get("is_market_open", False),
                    fifty_two_week_low=ftw.get("low", ""),
                    fifty_two_week_high=ftw.get("high", ""),
                )

            except httpx.TimeoutException:
                logger.warning(f"Timeout fetching {symbol} (attempt {attempt + 1}/{retries + 1})")
                if attempt < retries:
                    await asyncio.sleep(1.0)
            except Exception as e:
                logger.error(f"Error fetching {symbol}: {e}")
                if attempt < retries:
                    await asyncio.sleep(1.0)

        return None

    # ──────────────────────────────────────────────────────────────────────
    #  India Gold Conversion (Fix #3)
    # ──────────────────────────────────────────────────────────────────────

    def _wants_india_gold(self, query: str, symbol: str) -> bool:
        """Check if the user wants Indian gold prices."""
        q = query.lower()
        is_gold = symbol in ("XAU/USD", "XAG/USD")
        india_cues = ["india", "inr", "rupee", "rupees", "indian", "mumbai",
                      "delhi", "chennai", "bangalore", "bengaluru", "kolkata",
                      "hyderabad", "22k", "24k", "22 karat", "24 karat",
                      "per gram", "per 10 gram", "10 grams"]
        return is_gold and any(cue in q for cue in india_cues)

    async def _convert_gold_to_inr(self, gold_quote: FinanceQuote) -> str:
        """Convert XAU/USD spot price to Indian per-gram rates."""
        try:
            # Fetch USD/INR rate
            usd_inr_quote = await self._fetch_quote("USD/INR")
            if not usd_inr_quote:
                return "\n\n*(Could not fetch USD/INR rate for Indian conversion.)*"

            usd_per_ounce = float(gold_quote.price)
            usd_inr_rate = float(usd_inr_quote.price)

            # Price per gram in INR (24K)
            inr_per_gram_24k = (usd_per_ounce / TROY_OUNCE_TO_GRAMS) * usd_inr_rate
            inr_per_gram_22k = inr_per_gram_24k * KARAT_22_FACTOR
            inr_per_gram_18k = inr_per_gram_24k * KARAT_18_FACTOR

            inr_per_10g_24k = inr_per_gram_24k * 10
            inr_per_10g_22k = inr_per_gram_22k * 10

            return (
                f"\n\n**🇮🇳 Gold Prices in India** (converted at USD/INR ₹{usd_inr_rate:,.2f})\n"
                f"- **24K Gold:** ₹{inr_per_gram_24k:,.2f}/gram | ₹{inr_per_10g_24k:,.2f}/10 grams\n"
                f"- **22K Gold:** ₹{inr_per_gram_22k:,.2f}/gram | ₹{inr_per_10g_22k:,.2f}/10 grams\n"
                f"- **18K Gold:** ₹{inr_per_gram_18k:,.2f}/gram"
            )

        except Exception as e:
            logger.error(f"Gold INR conversion failed: {e}")
            return "\n\n*(Could not convert to INR at this time.)*"

    # ──────────────────────────────────────────────────────────────────────
    #  Response Formatting
    # ──────────────────────────────────────────────────────────────────────

    def _format_quote(self, q: FinanceQuote, india_gold_extra: str = "") -> str:
        """Format a FinanceQuote into a readable markdown response."""
        # If the user explicitly wants India gold, prioritize and return ONLY the India response
        if india_gold_extra:
            return india_gold_extra.strip()

        try:
            change_val = float(q.change)
            pct_val = float(q.percent_change)
        except (ValueError, TypeError):
            change_val = 0.0
            pct_val = 0.0

        arrow = "🟢 ▲" if change_val >= 0 else "🔴 ▼"
        sign = "+" if change_val >= 0 else ""
        market = "🟢 Open" if q.is_market_open else "🔴 Closed"

        parts = [
            f"## 📊 {q.name} ({q.symbol})\n",
            f"**Price:** {q.price} {q.currency}\n",
            f"**Change:** {arrow} {sign}{q.change} ({sign}{pct_val:.2f}%)\n",
            f"**Exchange:** {q.exchange} — Market: {market}\n",
        ]

        if q.fifty_two_week_low and q.fifty_two_week_high:
            parts.append(
                f"**52-Week Range:** {q.fifty_two_week_low} — {q.fifty_two_week_high}\n"
            )

        if india_gold_extra:
            parts.append(india_gold_extra)

        return "".join(parts)

    # ──────────────────────────────────────────────────────────────────────
    #  Cache helpers (Fix #2)
    # ──────────────────────────────────────────────────────────────────────

    def _get_cached(self, symbol: str) -> Optional[FinanceQuote]:
        entry = self._cache.get(symbol)
        if entry and (time.time() - entry.timestamp) < CACHE_TTL_SECONDS:
            return entry.quote
        if entry:
            del self._cache[symbol]
        return None

    def _set_cached(self, symbol: str, quote: FinanceQuote):
        self._cache[symbol] = _CacheEntry(quote=quote, timestamp=time.time())

    # ──────────────────────────────────────────────────────────────────────
    #  Rate-limiter helpers (Fix #4)
    # ──────────────────────────────────────────────────────────────────────

    def _can_request(self) -> bool:
        now = time.time()

        # Reset daily counter
        if now > self._day_reset:
            self._day_count = 0
            self._day_reset = now + 86400

        if self._day_count >= MAX_REQUESTS_PER_DAY:
            logger.warning("Daily rate limit reached")
            return False

        # Prune old minute entries
        self._minute_window = [t for t in self._minute_window if now - t < 60]
        if len(self._minute_window) >= MAX_REQUESTS_PER_MINUTE:
            logger.warning("Per-minute rate limit reached")
            return False

        return True

    def _record_request(self):
        self._minute_window.append(time.time())
        self._day_count += 1
