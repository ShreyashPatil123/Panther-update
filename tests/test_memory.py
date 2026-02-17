"""Tests for memory system."""
import pytest
import asyncio
from pathlib import Path
import tempfile
import shutil

from src.memory.memory_system import MemorySystem


@pytest.fixture
def temp_db():
    """Create temporary database directory."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
async def memory(temp_db):
    """Create a test memory system."""
    memory = MemorySystem(
        db_path=temp_db / "test.db",
        chroma_path=temp_db / "chroma"
    )
    await memory.initialize()
    yield memory
    await memory.close()


@pytest.mark.asyncio
async def test_memory_initialization(memory):
    """Test memory system initialization."""
    assert memory.conn is not None
    # ChromaDB may be unavailable on some Python versions (e.g. Python 3.14)
    # The system should still work with keyword-based fallback
    assert memory.conn is not None  # SQLite always available
    if memory._semantic_search_available:
        assert memory.chroma_client is not None
        assert memory.collection is not None


@pytest.mark.asyncio
async def test_add_message(memory):
    """Test adding a message."""
    await memory.add_message(
        role="user",
        content="Hello world",
        session_id="test_session"
    )

    messages = await memory.get_recent_messages(
        limit=10,
        session_id="test_session"
    )

    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello world"


@pytest.mark.asyncio
async def test_get_relevant_context(memory):
    """Test context retrieval (semantic or keyword based)."""
    # Add some messages
    await memory.add_message(
        role="user",
        content="I like Python programming",
        session_id="test_ctx"
    )
    await memory.add_message(
        role="user",
        content="The weather is nice today",
        session_id="test_ctx"
    )

    # Search for context using a word that is present in stored messages
    context = await memory.get_relevant_context(
        query="Python programming",
        limit=5,
        session_id="test_ctx"
    )

    # Should return at least one result
    assert len(context) > 0


@pytest.mark.asyncio
async def test_add_memory(memory):
    """Test adding long-term memory."""
    await memory.add_memory(
        memory_type="preference",
        content="User prefers dark mode",
        importance=8
    )

    memories = await memory.get_memories(memory_type="preference")
    assert len(memories) == 1
    assert memories[0]["type"] == "preference"


@pytest.mark.asyncio
async def test_session_management(memory):
    """Test session creation and retrieval."""
    await memory.create_session("session_1", "Test Session")
    await memory.create_session("session_2", "Another Session")

    sessions = await memory.get_sessions()
    assert len(sessions) == 2


@pytest.mark.asyncio
async def test_clear_session(memory):
    """Test clearing a session."""
    await memory.add_message(
        role="user",
        content="Message to be cleared",
        session_id="clear_test"
    )

    await memory.clear_session("clear_test")

    messages = await memory.get_recent_messages(
        limit=10,
        session_id="clear_test"
    )
    assert len(messages) == 0
