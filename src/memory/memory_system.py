"""Memory system with SQLite for structured data and ChromaDB for semantic search."""
import asyncio
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

# ChromaDB is optional — may not work on all Python versions
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    from chromadb.utils import embedding_functions
    _CHROMA_AVAILABLE = True
except Exception as _chroma_err:
    logger.warning(f"ChromaDB unavailable (semantic search disabled): {_chroma_err}")
    chromadb = None  # type: ignore
    _CHROMA_AVAILABLE = False


class MemorySystem:
    """Persistent memory system with semantic search capabilities."""

    def __init__(
        self,
        db_path: Path = Path("./data/agent.db"),
        chroma_path: Path = Path("./data/chroma"),
    ):
        """Initialize memory system.

        Args:
            db_path: Path to SQLite database
            chroma_path: Path to ChromaDB storage
        """
        self.db_path = Path(db_path)
        self.chroma_path = Path(chroma_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.chroma_path.mkdir(parents=True, exist_ok=True)

        self.conn: Optional[sqlite3.Connection] = None
        self.chroma_client = None
        self.collection = None
        self._semantic_search_available = False

        self._lock = asyncio.Lock()

    async def initialize(self):
        """Initialize database and vector store."""
        logger.info("Initializing memory system")

        async with self._lock:
            # Initialize SQLite
            self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self._create_tables()

            # Initialize ChromaDB (optional)
            if _CHROMA_AVAILABLE:
                try:
                    self.chroma_client = chromadb.PersistentClient(
                        path=str(self.chroma_path),
                        settings=ChromaSettings(
                            anonymized_telemetry=False,
                            allow_reset=True,
                        ),
                    )

                    # Use sentence transformers for embeddings
                    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                        model_name="all-MiniLM-L6-v2"
                    )

                    self.collection = self.chroma_client.get_or_create_collection(
                        name="conversations",
                        embedding_function=embedding_fn,
                        metadata={"description": "Conversation memory storage"},
                    )
                    self._semantic_search_available = True
                    logger.info("ChromaDB semantic search initialized")
                except Exception as e:
                    logger.warning(f"ChromaDB init failed (falling back to keyword search): {e}")
                    self._semantic_search_available = False
            else:
                logger.info("ChromaDB unavailable — using keyword-based context retrieval")

        logger.info("Memory system initialized successfully")

    def _create_tables(self):
        """Create database schema."""
        cursor = self.conn.cursor()

        # Conversations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            )
        """)

        # Sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            )
        """)

        # Memories table for important facts/insights
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_type TEXT NOT NULL,
                content TEXT NOT NULL,
                importance INTEGER DEFAULT 1,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            )
        """)

        # File access history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS file_access (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                action TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                summary TEXT,
                metadata TEXT
            )
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_session
            ON conversations(session_id, timestamp)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_type
            ON memories(memory_type, timestamp)
        """)

        self.conn.commit()

    async def add_message(
        self,
        role: str,
        content: str,
        session_id: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Store a conversation message.

        Args:
            role: Message role (user/assistant/system)
            content: Message content
            session_id: Session identifier
            metadata: Optional metadata dictionary
        """
        async with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO conversations (session_id, role, content, metadata)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, content, json.dumps(metadata) if metadata else None),
            )
            self.conn.commit()

            # Add to vector store for semantic search (if available)
            message_id = cursor.lastrowid
            if self._semantic_search_available and self.collection is not None:
                try:
                    self.collection.add(
                        documents=[content],
                        metadatas=[
                            {
                                "role": role,
                                "session_id": session_id,
                                "timestamp": datetime.now().isoformat(),
                                "db_id": str(message_id),
                            }
                        ],
                        ids=[f"msg_{message_id}_{uuid.uuid4().hex[:8]}"],
                    )
                except Exception as e:
                    logger.debug(f"ChromaDB add failed (non-critical): {e}")

            # Ensure session exists without resetting title/created_at if it does
            cursor.execute(
                """
                INSERT OR IGNORE INTO sessions (id, title)
                VALUES (?, ?)
                """,
                (session_id, f"Session {session_id[:8]}"),
            )

            # Update session timestamp (preserve title)
            cursor.execute(
                """
                UPDATE sessions SET updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (session_id,),
            )
            self.conn.commit()

        logger.debug(f"Stored message: {role} - {content[:50]}...")

    async def get_relevant_context(
        self, query: str, limit: int = 5, session_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant context using semantic search (or keyword fallback).

        Args:
            query: Search query
            limit: Maximum number of results
            session_id: Optional session filter

        Returns:
            List of relevant messages
        """
        # Try semantic search first
        if self._semantic_search_available and self.collection is not None:
            try:
                where_filter = {"session_id": session_id} if session_id else None
                results = self.collection.query(
                    query_texts=[query],
                    n_results=limit,
                    where=where_filter,
                )
                contexts = []
                if results and results["documents"] and results["documents"][0]:
                    for i, doc in enumerate(results["documents"][0]):
                        meta = results["metadatas"][0][i] if results["metadatas"] else {}
                        contexts.append({
                            "content": doc,
                            "role": meta.get("role", "unknown"),
                            "timestamp": meta.get("timestamp"),
                        })
                return contexts
            except Exception as e:
                logger.debug(f"Semantic search failed, using keyword fallback: {e}")

        # Keyword fallback: search by simple LIKE query
        return await self._keyword_context_search(query, limit, session_id)

    async def _keyword_context_search(
        self, query: str, limit: int, session_id: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Simple keyword-based context retrieval from SQLite."""
        async with self._lock:
            cursor = self.conn.cursor()
            # Use FTS-style LIKE search
            words = query.split()[:5]  # Use first 5 words
            if not words:
                return []

            # Build LIKE condition for each word
            conditions = " OR ".join(["content LIKE ?" for _ in words])
            params = [f"%{w}%" for w in words]

            if session_id:
                query_sql = f"""
                    SELECT role, content, timestamp FROM conversations
                    WHERE session_id = ? AND ({conditions})
                    ORDER BY timestamp DESC LIMIT ?
                """
                params = [session_id] + params + [limit]
            else:
                query_sql = f"""
                    SELECT role, content, timestamp FROM conversations
                    WHERE {conditions}
                    ORDER BY timestamp DESC LIMIT ?
                """
                params = params + [limit]

            try:
                cursor.execute(query_sql, params)
                rows = cursor.fetchall()
                return [
                    {
                        "content": row["content"],
                        "role": row["role"],
                        "timestamp": row["timestamp"],
                    }
                    for row in rows
                ]
            except Exception as e:
                logger.error(f"Keyword search failed: {e}")
                return []

    async def get_recent_messages(
        self,
        limit: int = 10,
        session_id: str = "default",
    ) -> List[Dict[str, Any]]:
        """Get recent conversation history.

        Args:
            limit: Maximum number of messages
            session_id: Session identifier

        Returns:
            List of recent messages
        """
        async with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT id, role, content, timestamp, metadata
                FROM conversations
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            )

            messages = []
            for row in cursor.fetchall():
                messages.append(
                    {
                        "id": row[0],
                        "role": row[1],
                        "content": row[2],
                        "timestamp": row[3],
                        "metadata": json.loads(row[4]) if row[4] else None,
                    }
                )

        return list(reversed(messages))  # Return in chronological order

    async def add_memory(
        self,
        memory_type: str,
        content: str,
        importance: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Store a long-term memory.

        Args:
            memory_type: Type of memory (fact, preference, task, etc.)
            content: Memory content
            importance: Importance level (1-10)
            metadata: Optional metadata
        """
        async with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO memories (memory_type, content, importance, metadata)
                VALUES (?, ?, ?, ?)
                """,
                (
                    memory_type,
                    content,
                    importance,
                    json.dumps(metadata) if metadata else None,
                ),
            )
            self.conn.commit()

            # Add to vector store (if available)
            memory_id = cursor.lastrowid
            if self._semantic_search_available and self.collection is not None:
                try:
                    self.collection.add(
                        documents=[content],
                        metadatas=[
                            {
                                "type": memory_type,
                                "importance": importance,
                                "timestamp": datetime.now().isoformat(),
                                "db_id": str(memory_id),
                            }
                        ],
                        ids=[f"mem_{memory_id}_{uuid.uuid4().hex[:8]}"],
                    )
                except Exception as e:
                    logger.debug(f"ChromaDB memory add failed (non-critical): {e}")

        logger.info(f"Stored {memory_type} memory: {content[:50]}...")

    async def get_memories(
        self,
        memory_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Retrieve stored memories.

        Args:
            memory_type: Optional type filter
            limit: Maximum number of memories

        Returns:
            List of memories
        """
        async with self._lock:
            cursor = self.conn.cursor()

            if memory_type:
                cursor.execute(
                    """
                    SELECT id, memory_type, content, importance, timestamp
                    FROM memories
                    WHERE memory_type = ?
                    ORDER BY importance DESC, timestamp DESC
                    LIMIT ?
                    """,
                    (memory_type, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, memory_type, content, importance, timestamp
                    FROM memories
                    ORDER BY importance DESC, timestamp DESC
                    LIMIT ?
                    """,
                    (limit,),
                )

            memories = []
            for row in cursor.fetchall():
                memories.append(
                    {
                        "id": row[0],
                        "type": row[1],
                        "content": row[2],
                        "importance": row[3],
                        "timestamp": row[4],
                    }
                )

        return memories

    async def create_session(self, session_id: str, title: Optional[str] = None):
        """Create a new conversation session.

        Args:
            session_id: Unique session identifier
            title: Optional session title
        """
        async with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO sessions (id, title, created_at, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (session_id, title or f"Session {session_id[:8]}"),
            )
            self.conn.commit()
        logger.info(f"Created session: {session_id}")

    async def update_session_title(self, session_id: str, title: str):
        """Update the title of an existing session.

        Args:
            session_id: Session identifier
            title: New title for the session
        """
        async with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE sessions SET title = ? WHERE id = ?",
                (title, session_id),
            )
            self.conn.commit()
        logger.info(f"Updated session title: {session_id} → {title}")

    async def get_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get list of conversation sessions.

        Args:
            limit: Maximum number of sessions

        Returns:
            List of sessions
        """
        async with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM sessions
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            )

            sessions = []
            for row in cursor.fetchall():
                sessions.append(
                    {
                        "id": row[0],
                        "title": row[1],
                        "created_at": row[2],
                        "updated_at": row[3],
                    }
                )

        return sessions

    async def clear_session(self, session_id: str = "default"):
        """Clear a conversation session.

        Args:
            session_id: Session to clear
        """
        async with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "DELETE FROM conversations WHERE session_id = ?",
                (session_id,),
            )
            self.conn.commit()

            # Also delete from ChromaDB (if available)
            if self._semantic_search_available and self.collection is not None:
                try:
                    self.collection.delete(where={"session_id": session_id})
                except Exception as e:
                    logger.debug(f"ChromaDB delete failed (non-critical): {e}")

        logger.info(f"Cleared session: {session_id}")

    async def delete_session(self, session_id: str):
        """Delete a session completely.

        Args:
            session_id: Session to delete
        """
        async with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "DELETE FROM conversations WHERE session_id = ?",
                (session_id,),
            )
            cursor.execute(
                "DELETE FROM sessions WHERE id = ?",
                (session_id,),
            )
            self.conn.commit()

            # Delete from ChromaDB (if available)
            if self._semantic_search_available and self.collection is not None:
                try:
                    self.collection.delete(where={"session_id": session_id})
                except Exception as e:
                    logger.debug(f"ChromaDB delete failed (non-critical): {e}")

        logger.info(f"Deleted session: {session_id}")

    async def log_file_access(
        self,
        file_path: str,
        action: str,
        summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Log file access.

        Args:
            file_path: Path to file
            action: Action performed (read, write, etc.)
            summary: Optional summary
            metadata: Optional metadata
        """
        async with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO file_access (file_path, action, summary, metadata)
                VALUES (?, ?, ?, ?)
                """,
                (
                    file_path,
                    action,
                    summary,
                    json.dumps(metadata) if metadata else None,
                ),
            )
            self.conn.commit()

        logger.debug(f"Logged file access: {action} - {file_path}")

    async def get_file_history(self, file_path: Optional[str] = None, limit: int = 50):
        """Get file access history.

        Args:
            file_path: Optional file path filter
            limit: Maximum number of records

        Returns:
            List of file access records
        """
        async with self._lock:
            cursor = self.conn.cursor()

            if file_path:
                cursor.execute(
                    """
                    SELECT file_path, action, timestamp, summary
                    FROM file_access
                    WHERE file_path = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (file_path, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT file_path, action, timestamp, summary
                    FROM file_access
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (limit,),
                )

            history = []
            for row in cursor.fetchall():
                history.append(
                    {
                        "file_path": row[0],
                        "action": row[1],
                        "timestamp": row[2],
                        "summary": row[3],
                    }
                )

        return history

    async def search_memory(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search all memory (conversations and memories) by semantic similarity or keyword.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching memories
        """
        # Try semantic search first
        if self._semantic_search_available and self.collection is not None:
            try:
                results = self.collection.query(
                    query_texts=[query],
                    n_results=limit,
                )

                matches = []
                if results and results["documents"] and results["documents"][0]:
                    for i, doc in enumerate(results["documents"][0]):
                        meta = results["metadatas"][0][i] if results["metadatas"] else {}
                        matches.append({
                            "content": doc,
                            "role": meta.get("role", "unknown"),
                            "metadata": meta,
                        })
                return matches
            except Exception as e:
                logger.debug(f"Semantic search failed: {e}")

        # Keyword fallback
        return await self._keyword_context_search(query, limit, session_id=None)

    async def close(self):
        """Close database connections."""
        if self.conn:
            self.conn.close()
            self.conn = None
        logger.info("Memory system closed")
