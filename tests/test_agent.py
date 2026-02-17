"""Tests for agent orchestrator."""
import pytest


@pytest.mark.asyncio
async def test_agent_initialization(agent_orchestrator):
    """Test agent initialization."""
    assert agent_orchestrator is not None
    assert agent_orchestrator.memory is not None


@pytest.mark.asyncio
async def test_intent_classification(agent_orchestrator):
    """Test intent classification."""
    # File operation intent
    intent = await agent_orchestrator._classify_intent("Open the file document.txt")
    assert intent == "file_operation"

    # Browser intent
    intent = await agent_orchestrator._classify_intent("Browse to google.com")
    assert intent == "browser_task"

    # Research intent
    intent = await agent_orchestrator._classify_intent("Research about climate change")
    assert intent == "research"

    # Chat intent
    intent = await agent_orchestrator._classify_intent("Hello, how are you?")
    assert intent == "chat"


@pytest.mark.asyncio
async def test_build_messages(agent_orchestrator):
    """Test message building."""
    message = "Test message"
    context = [{"role": "user", "content": "Previous message"}]
    history: list = []  # empty history

    messages = agent_orchestrator._build_messages(message, context, history)

    assert len(messages) >= 2
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == message


@pytest.mark.asyncio
async def test_session_management(agent_orchestrator):
    """Test session creation and switching."""
    # Create new session
    session_id = await agent_orchestrator.new_session()
    assert session_id is not None
    assert agent_orchestrator.current_session_id == session_id

    # Get sessions
    sessions = await agent_orchestrator.get_sessions()
    assert len(sessions) >= 1

    # Clear session
    await agent_orchestrator.clear_current_session()
