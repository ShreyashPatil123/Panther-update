"""Web Research Engine - Deep research with source verification."""
import asyncio
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional
from urllib.parse import quote_plus, urlparse

import httpx
from loguru import logger

if TYPE_CHECKING:
    from src.api.nvidia_client import NVIDIAClient


@dataclass
class ResearchSource:
    """A research source with URL, title, and content snippet."""

    url: str
    title: str
    snippet: str
    content: str = ""


@dataclass
class ResearchResult:
    """Result of a deep research query."""

    query: str
    sources: List[ResearchSource] = field(default_factory=list)
    synthesized_answer: str = ""
    sub_queries: List[str] = field(default_factory=list)


class ResearchEngine:
    """Deep research engine using DuckDuckGo and web scraping."""

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
            follow_redirects=True,
        )
        logger.info("ResearchEngine initialized")

    async def deep_research(
        self,
        query: str,
        nvidia_client: Optional["NVIDIAClient"] = None,
        max_sources: int = 5,
        model: str = "",
    ) -> ResearchResult:
        """Perform deep research on a topic.

        Args:
            query: Research query
            nvidia_client: Optional LLM client for synthesis
            max_sources: Maximum number of sources to fetch

        Returns:
            ResearchResult with sources and synthesized answer
        """
        logger.info(f"Starting deep research: {query}")
        result = ResearchResult(query=query)

        # Step 1: Search DuckDuckGo
        sources = await self._search_ddg(query, max_results=max_sources)
        result.sources = sources

        # Step 2: Fetch content from top sources
        fetch_tasks = [self._fetch_page_content(src) for src in sources[:3]]
        fetched = await asyncio.gather(*fetch_tasks, return_exceptions=True)
        for src, content in zip(sources[:3], fetched):
            if isinstance(content, str):
                src.content = content

        # Step 3: Synthesize with LLM if available
        if nvidia_client and sources:
            result.synthesized_answer = await self._synthesize_results(
                sources, query, nvidia_client, model=model
            )
        else:
            # Fallback: concatenate snippets
            result.synthesized_answer = self._basic_synthesis(sources, query)

        logger.info(f"Research complete: {len(sources)} sources found")
        return result

    async def _search_ddg(self, query: str, max_results: int = 5) -> List[ResearchSource]:
        """Search DuckDuckGo for the query.

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            List of research sources
        """
        sources = []

        # Try DuckDuckGo instant answer API first
        try:
            instant_sources = await self._ddg_instant_answer(query)
            sources.extend(instant_sources)
        except Exception as e:
            logger.warning(f"DuckDuckGo instant answer failed: {e}")

        # Try DuckDuckGo HTML search
        if len(sources) < max_results:
            try:
                html_sources = await self._ddg_html_search(query, max_results)
                # Deduplicate by URL
                existing_urls = {s.url for s in sources}
                for src in html_sources:
                    if src.url not in existing_urls:
                        sources.append(src)
                        existing_urls.add(src.url)
            except Exception as e:
                logger.warning(f"DuckDuckGo HTML search failed: {e}")

        return sources[:max_results]

    async def _ddg_instant_answer(self, query: str) -> List[ResearchSource]:
        """Use DuckDuckGo instant answer API."""
        url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
        response = await self.client.get(url)
        response.raise_for_status()
        data = response.json()

        sources = []

        # Abstract (main result)
        if data.get("AbstractText") and data.get("AbstractURL"):
            sources.append(ResearchSource(
                url=data["AbstractURL"],
                title=data.get("Heading", query),
                snippet=data["AbstractText"][:500],
            ))

        # Related topics
        for topic in data.get("RelatedTopics", [])[:3]:
            if isinstance(topic, dict) and topic.get("FirstURL") and topic.get("Text"):
                sources.append(ResearchSource(
                    url=topic["FirstURL"],
                    title=topic.get("Text", "")[:80],
                    snippet=topic.get("Text", "")[:300],
                ))

        return sources

    async def _ddg_html_search(self, query: str, max_results: int = 5) -> List[ResearchSource]:
        """Scrape DuckDuckGo HTML search results."""
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            html = response.text
        except Exception as e:
            logger.warning(f"DDG HTML search request failed: {e}")
            return []

        sources = []

        # Parse result snippets using regex (avoids BeautifulSoup dependency)
        # DuckDuckGo HTML results pattern
        result_blocks = re.findall(
            r'class="result__body".*?class="result__snippet"[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        )

        # Extract URLs and titles
        url_title_pattern = re.findall(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        )

        snippet_pattern = re.findall(
            r'class="result__snippet"[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        )

        for i, (url_match, title_match) in enumerate(url_title_pattern[:max_results]):
            # Clean URL (DDG wraps in redirect)
            clean_url = self._extract_real_url(url_match)
            clean_title = re.sub(r"<[^>]+>", "", title_match).strip()
            snippet = ""
            if i < len(snippet_pattern):
                snippet = re.sub(r"<[^>]+>", "", snippet_pattern[i]).strip()

            if clean_url and clean_title:
                sources.append(ResearchSource(
                    url=clean_url,
                    title=clean_title,
                    snippet=snippet[:300],
                ))

        return sources

    def _extract_real_url(self, ddg_url: str) -> str:
        """Extract real URL from DuckDuckGo redirect URL."""
        # DDG sometimes uses //duckduckgo.com/l/?uddg=ENCODED_URL
        uddg_match = re.search(r"uddg=([^&]+)", ddg_url)
        if uddg_match:
            from urllib.parse import unquote
            return unquote(uddg_match.group(1))
        # Or direct URL
        if ddg_url.startswith("http"):
            return ddg_url
        return ""

    async def _fetch_page_content(self, source: ResearchSource) -> str:
        """Fetch and extract readable text from a webpage.

        Args:
            source: Research source to fetch

        Returns:
            Extracted text content (max 2000 chars)
        """
        try:
            parsed = urlparse(source.url)
            if parsed.scheme not in ("http", "https"):
                return source.snippet

            response = await self.client.get(source.url, timeout=10.0)
            response.raise_for_status()
            html = response.text

            # Remove script/style blocks
            html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)

            # Extract text from tags
            text = re.sub(r"<[^>]+>", " ", html)

            # Clean whitespace
            text = re.sub(r"\s+", " ", text).strip()

            # Return first 2000 chars of useful content
            return text[:2000]

        except Exception as e:
            logger.debug(f"Failed to fetch {source.url}: {e}")
            return source.snippet

    async def _synthesize_results(
        self,
        sources: List[ResearchSource],
        query: str,
        nvidia_client: "NVIDIAClient",
        model: str = "",
    ) -> str:
        """Synthesize research results using LLM.

        Args:
            sources: Research sources with content
            query: Original query
            nvidia_client: NVIDIA LLM client

        Returns:
            Synthesized answer
        """
        # Build context from sources
        context_parts = []
        for i, src in enumerate(sources, 1):
            content = src.content or src.snippet
            context_parts.append(
                f"Source {i}: {src.title}\nURL: {src.url}\nContent: {content[:500]}"
            )

        context = "\n\n".join(context_parts)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a research analyst. Synthesize the provided sources into a "
                    "clear, comprehensive answer. Include key facts and cite sources by number. "
                    "Be concise and factual."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Research query: {query}\n\n"
                    f"Sources:\n{context}\n\n"
                    "Please provide a synthesized answer based on these sources."
                ),
            },
        ]

        response_chunks = []
        try:
            async for chunk in nvidia_client.chat_completion(
                messages, model=model, stream=False, max_tokens=1024
            ):
                response_chunks.append(chunk)
        except Exception as e:
            logger.error(f"LLM synthesis failed: {e}")
            return self._basic_synthesis(sources, query)

        return "".join(response_chunks)

    def _basic_synthesis(self, sources: List[ResearchSource], query: str) -> str:
        """Basic synthesis without LLM - just concatenate snippets."""
        if not sources:
            return f"No results found for: {query}"

        parts = [f"Research results for: **{query}**\n"]
        for i, src in enumerate(sources, 1):
            content = src.content or src.snippet
            parts.append(f"\n**Source {i}: {src.title}**")
            parts.append(f"URL: {src.url}")
            if content:
                parts.append(content[:300])

        return "\n".join(parts)

    def format_result_for_display(self, result: ResearchResult) -> str:
        """Format research result for chat display.

        Args:
            result: Research result to format

        Returns:
            Formatted string for display
        """
        lines = [f"## Research: {result.query}\n"]

        if result.synthesized_answer:
            lines.append(result.synthesized_answer)
            lines.append("")

        if result.sources:
            lines.append("\n### Sources")
            for i, src in enumerate(result.sources, 1):
                lines.append(f"{i}. [{src.title}]({src.url})")

        return "\n".join(lines)

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
