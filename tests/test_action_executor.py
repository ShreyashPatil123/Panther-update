"""Tests for ActionExecutor."""

import pytest
from unittest.mock import AsyncMock, MagicMock, PropertyMock

from src.agent.action_executor import ActionExecutor, ActionResult


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _mock_browser():
    browser = MagicMock()
    browser.navigate = AsyncMock()
    browser.get_title = AsyncMock(return_value="Test Page")
    browser.url = "https://example.com"

    # Mock page
    page = MagicMock()
    page.keyboard = MagicMock()
    page.keyboard.type = AsyncMock()
    page.keyboard.press = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    browser.page = page

    return browser


def _mock_dom():
    dom = MagicMock()
    dom.click = AsyncMock()
    dom.type_text = AsyncMock()
    dom.scroll = AsyncMock()
    dom.wait_for_element = AsyncMock()
    return dom


# ── Tests ────────────────────────────────────────────────────────────────────


class TestActionExecutor:
    @pytest.mark.asyncio
    async def test_navigate(self):
        browser = _mock_browser()
        dom = _mock_dom()
        executor = ActionExecutor(browser, dom)

        result = await executor.execute("navigate", {"url": "https://google.com"})
        assert result.success is True
        assert "google.com" in result.observation
        browser.navigate.assert_awaited_once_with("https://google.com")

    @pytest.mark.asyncio
    async def test_click_with_selector(self):
        browser = _mock_browser()
        dom = _mock_dom()
        executor = ActionExecutor(browser, dom)

        result = await executor.execute("click", {"selector": "#btn"})
        assert result.success is True
        dom.click.assert_awaited_once_with(selector="#btn")

    @pytest.mark.asyncio
    async def test_click_without_selector(self):
        browser = _mock_browser()
        dom = _mock_dom()
        executor = ActionExecutor(browser, dom)

        result = await executor.execute("click", {})
        assert result.success is False
        assert result.error == "No selector or SOM label provided"

    @pytest.mark.asyncio
    async def test_type_with_selector(self):
        browser = _mock_browser()
        dom = _mock_dom()
        executor = ActionExecutor(browser, dom)

        result = await executor.execute("type", {"text": "hello", "selector": "#q"})
        assert result.success is True
        dom.type_text.assert_awaited_once_with("#q", "hello")

    @pytest.mark.asyncio
    async def test_type_with_enter(self):
        browser = _mock_browser()
        dom = _mock_dom()
        executor = ActionExecutor(browser, dom)

        result = await executor.execute(
            "type", {"text": "hello", "press_enter": True}
        )
        assert result.success is True
        browser.page.keyboard.press.assert_awaited_once_with("Enter")

    @pytest.mark.asyncio
    async def test_scroll(self):
        browser = _mock_browser()
        dom = _mock_dom()
        executor = ActionExecutor(browser, dom)

        result = await executor.execute("scroll", {"direction": "down", "amount_px": 300})
        assert result.success is True
        assert "300px" in result.observation
        dom.scroll.assert_awaited_once_with("down", 300)

    @pytest.mark.asyncio
    async def test_wait_with_duration(self):
        browser = _mock_browser()
        dom = _mock_dom()
        executor = ActionExecutor(browser, dom)

        result = await executor.execute("wait", {"duration_ms": 500})
        assert result.success is True
        browser.page.wait_for_timeout.assert_awaited_once_with(500)

    @pytest.mark.asyncio
    async def test_wait_with_condition(self):
        browser = _mock_browser()
        dom = _mock_dom()
        executor = ActionExecutor(browser, dom)

        result = await executor.execute("wait", {"condition": ".loaded"})
        assert result.success is True
        dom.wait_for_element.assert_awaited_once_with(".loaded")

    @pytest.mark.asyncio
    async def test_finish(self):
        browser = _mock_browser()
        dom = _mock_dom()
        executor = ActionExecutor(browser, dom)

        result = await executor.execute("finish", {"result": "Done!"})
        assert result.success is True
        assert result.observation == "Done!"

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        browser = _mock_browser()
        dom = _mock_dom()
        executor = ActionExecutor(browser, dom)

        result = await executor.execute("fly_to_moon", {})
        assert result.success is False
        assert "Unknown action" in result.error
