"""Security Filter — structural pipeline guards for browser automation.

URL validation, DOM prompt-injection sanitisation, and action guards
that run on EVERY step of the automation loop.

Architecture reference: §12
"""

import re
from typing import Dict, List, Set
from urllib.parse import urlparse

from loguru import logger


class SecurityError(Exception):
    """Raised when a security constraint is violated."""


class SecurityFilter:
    """Structural security guards for the automation pipeline."""

    def __init__(
        self,
        blocked_domains: Set[str] | None = None,
        allowed_domains: Set[str] | None = None,
        allowed_js_patterns: List[str] | None = None,
        enable_injection_filter: bool = True,
    ):
        """Initialise the security filter.

        Args:
            blocked_domains: Domains that are always blocked
            allowed_domains: If non-empty, only these domains are allowed
            allowed_js_patterns: Regex patterns for allowed JavaScript execution
            enable_injection_filter: Whether to strip prompt injection patterns
        """
        self.blocked_domains = blocked_domains or {"evil.com", "malware.xyz"}
        self.allowed_domains = allowed_domains or set()
        self.allowed_js_patterns = allowed_js_patterns or [
            r"^window\.scrollBy\(",
            r"^window\.scrollTo\(",
            r"^document\.querySelectorAll\(",
            r"^document\.querySelector\(",
            r"^\(\) =>",
        ]
        self.enable_injection_filter = enable_injection_filter

        # Known prompt injection patterns
        self._injection_patterns = [
            r"ignore previous instructions",
            r"you are now",
            r"system:",
            r"<\|.*?\|>",
            r"IMPORTANT: override",
            r"disregard all prior",
            r"forget everything",
        ]

    # ── URL validation ───────────────────────────────────────────────────

    def validate_url(self, url: str) -> bool:
        """Validate a URL against blocklist/allowlist.

        Args:
            url: URL to validate

        Returns:
            True if URL is safe

        Raises:
            SecurityError: If URL is blocked
        """
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Strip port number for matching
        if ":" in domain:
            domain = domain.split(":")[0]

        # Block check
        if domain in self.blocked_domains:
            raise SecurityError(f"Blocked domain: {domain}")

        # Allow check (empty = allow all)
        if self.allowed_domains and domain not in self.allowed_domains:
            raise SecurityError(
                f"Domain not in allowlist: {domain}"
            )

        return True

    # ── DOM sanitisation ─────────────────────────────────────────────────

    def sanitize_dom_for_llm(self, dom_text: str) -> str:
        """Remove potential prompt injection patterns from page content.

        Args:
            dom_text: Raw DOM text to sanitise

        Returns:
            Sanitised DOM text with injections replaced by [REDACTED]
        """
        if not self.enable_injection_filter:
            return dom_text

        sanitised = dom_text
        for pattern in self._injection_patterns:
            sanitised = re.sub(
                pattern, "[REDACTED]", sanitised, flags=re.IGNORECASE
            )
        return sanitised

    # ── Action validation ────────────────────────────────────────────────

    def validate_action(self, action_name: str, params: Dict) -> bool:
        """Validate an action before execution.

        Args:
            action_name: Name of the action
            params: Action parameters

        Returns:
            True if action is safe

        Raises:
            SecurityError: If action violates security rules
        """
        # Validate navigation URLs
        if action_name == "navigate":
            url = params.get("url", "")
            self.validate_url(url)

        # Validate JS execution
        if action_name == "execute_js":
            script = params.get("script", "")
            if not any(
                re.match(p, script) for p in self.allowed_js_patterns
            ):
                raise SecurityError(f"Unauthorized JS: {script[:100]}")

        return True
