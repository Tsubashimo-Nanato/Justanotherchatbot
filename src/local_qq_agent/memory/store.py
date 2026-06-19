from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from typing import Any

from local_qq_agent.paths import ensure_parent


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def encode_metadata(metadata: dict[str, Any] | None) -> str:
    return json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)


def decode_metadata(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        return {}
    return decoded


@dataclass(frozen=True)
class EventRecord:
    id: int
    created_at: str
    source: str
    kind: str
    content: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class MemoryRecord:
    id: int
    created_at: str
    updated_at: str
    kind: str
    summary: str
    confidence: float
    metadata: dict[str, Any]


class SQLiteMemoryStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        ensure_parent(database_path)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_events_created_at
                    ON events(created_at);

                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_memories_kind
                    ON memories(kind);
                """
            )

    def append_event(
        self,
        *,
        source: str,
        kind: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> EventRecord:
        source = source.strip()
        kind = kind.strip()
        content = content.strip()
        if not source:
            raise ValueError("event source must not be empty")
        if not kind:
            raise ValueError("event kind must not be empty")
        if not content:
            raise ValueError("event content must not be empty")

        created_at = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO events(created_at, source, kind, content, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (created_at, source, kind, content, encode_metadata(metadata)),
            )
            event_id = int(cursor.lastrowid)

        return EventRecord(
            id=event_id,
            created_at=created_at,
            source=source,
            kind=kind,
            content=content,
            metadata=metadata or {},
        )

    def add_memory(
        self,
        *,
        kind: str,
        summary: str,
        confidence: float = 0.7,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        kind = kind.strip()
        summary = summary.strip()
        if not kind:
            raise ValueError("memory kind must not be empty")
        if not summary:
            raise ValueError("memory summary must not be empty")
        if confidence < 0 or confidence > 1:
            raise ValueError(f"memory confidence must be between 0 and 1, got {confidence}")

        now = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO memories(created_at, updated_at, kind, summary, confidence, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now, now, kind, summary, confidence, encode_metadata(metadata)),
            )
            memory_id = int(cursor.lastrowid)

        return MemoryRecord(
            id=memory_id,
            created_at=now,
            updated_at=now,
            kind=kind,
            summary=summary,
            confidence=confidence,
            metadata=metadata or {},
        )

    def update_memory(
        self,
        *,
        memory_id: int,
        kind: str,
        summary: str,
        confidence: float,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        kind = kind.strip()
        summary = summary.strip()
        if memory_id <= 0:
            raise ValueError(f"memory_id must be positive, got {memory_id}")
        if not kind:
            raise ValueError("memory kind must not be empty")
        if not summary:
            raise ValueError("memory summary must not be empty")
        if confidence < 0 or confidence > 1:
            raise ValueError(f"memory confidence must be between 0 and 1, got {confidence}")

        now = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE memories
                SET updated_at = ?, kind = ?, summary = ?, confidence = ?, metadata_json = ?
                WHERE id = ?
                """,
                (now, kind, summary, confidence, encode_metadata(metadata), memory_id),
            )
            if cursor.rowcount <= 0:
                raise KeyError(f"memory not found: {memory_id}")
            row = connection.execute(
                """
                SELECT id, created_at, updated_at, kind, summary, confidence, metadata_json
                FROM memories
                WHERE id = ?
                """,
                (memory_id,),
            ).fetchone()

        return self._memory_from_row(row)

    def delete_memory_by_id(self, memory_id: int) -> MemoryRecord | None:
        if memory_id <= 0:
            raise ValueError(f"memory_id must be positive, got {memory_id}")

        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, created_at, updated_at, kind, summary, confidence, metadata_json
                FROM memories
                WHERE id = ?
                """,
                (memory_id,),
            ).fetchone()
            if row is None:
                return None
            memory = self._memory_from_row(row)
            connection.execute("DELETE FROM memories WHERE id = ?", (memory_id,))

        return memory

    def recent_events(self, limit: int = 30, *, newest_first: bool = False) -> list[EventRecord]:
        if limit <= 0:
            return []

        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, source, kind, content, metadata_json
                FROM events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        events = [self._event_from_row(row) for row in rows]
        if not newest_first:
            events.reverse()
        return events

    def events_since(self, event_id: int, limit: int = 1000) -> list[EventRecord]:
        if limit <= 0:
            return []

        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, source, kind, content, metadata_json
                FROM events
                WHERE id > ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (max(event_id, 0), limit),
            ).fetchall()

        return [self._event_from_row(row) for row in rows]

    def search_memories(self, query: str, limit: int = 8) -> list[MemoryRecord]:
        query = query.strip()
        if not query or limit <= 0:
            return []

        like_query = f"%{query}%"
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, updated_at, kind, summary, confidence, metadata_json
                FROM memories
                WHERE summary LIKE ? OR kind LIKE ?
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (like_query, like_query, limit),
            ).fetchall()

        return [self._memory_from_row(row) for row in rows]

    def recent_memories(self, limit: int = 8, *, newest_first: bool = False) -> list[MemoryRecord]:
        if limit <= 0:
            return []

        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, updated_at, kind, summary, confidence, metadata_json
                FROM memories
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        memories = [self._memory_from_row(row) for row in rows]
        if not newest_first:
            memories.reverse()
        return memories

    def delete_memories_matching(self, query: str, limit: int = 50) -> list[MemoryRecord]:
        query = query.strip()
        if not query or limit <= 0:
            return []

        like_query = f"%{query}%"
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, updated_at, kind, summary, confidence, metadata_json
                FROM memories
                WHERE summary LIKE ? OR kind LIKE ?
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (like_query, like_query, limit),
            ).fetchall()
            memories = [self._memory_from_row(row) for row in rows]
            if memories:
                ids = [memory.id for memory in memories]
                placeholders = ",".join("?" for _ in ids)
                connection.execute(f"DELETE FROM memories WHERE id IN ({placeholders})", ids)

        return memories

    def status(self) -> dict[str, Any]:
        with self.connect() as connection:
            event_count = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            memory_count = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

        return {
            "database_path": str(self.database_path),
            "exists": self.database_path.exists(),
            "event_count": event_count,
            "memory_count": memory_count,
        }

    def _event_from_row(self, row: sqlite3.Row) -> EventRecord:
        return EventRecord(
            id=int(row["id"]),
            created_at=str(row["created_at"]),
            source=str(row["source"]),
            kind=str(row["kind"]),
            content=str(row["content"]),
            metadata=decode_metadata(row["metadata_json"]),
        )

    def _memory_from_row(self, row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=int(row["id"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            kind=str(row["kind"]),
            summary=str(row["summary"]),
            confidence=float(row["confidence"]),
            metadata=decode_metadata(row["metadata_json"]),
        )
