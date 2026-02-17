"""Pytest configuration and fixtures."""
import asyncio
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from src.config import Settings
from src.core.agent import AgentOrchestrator
from src.memory.memory_system import MemorySystem


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def temp_db():
    """Create a temporary database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        chroma_path = Path(tmpdir) / "chroma"
        yield db_path, chroma_path


@pytest_asyncio.fixture
async def memory_system(temp_db):
    """Create a memory system with temporary storage."""
    db_path, chroma_path = temp_db
    memory = MemorySystem(db_path=db_path, chroma_path=chroma_path)
    await memory.initialize()
    yield memory
    await memory.close()


@pytest_asyncio.fixture
async def agent_orchestrator():
    """Create an agent orchestrator with test configuration."""
    config = Settings(
        nvidia_api_key="test_key",
        db_path=Path("./data/test.db"),
        chroma_path=Path("./data/test_chroma"),
    )
    agent = AgentOrchestrator(config)
    await agent.initialize()
    yield agent
    await agent.close()
