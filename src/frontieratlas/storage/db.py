"""SQLite persistence: idempotent upserts, audit history, checkpoints, source runs.

SQLite is the local-development database for this submission. The schema is
deliberately PostgreSQL-compatible: stable text primary keys, JSONB-ready
payloads, unique constraints, and transactional batch writes.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from ..common.config import display_path
from ..common.text import content_hash
from ..schemas import EntityMapping

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    record_id      TEXT PRIMARY KEY,
    record_type    TEXT NOT NULL,
    source_name    TEXT NOT NULL,
    payload        TEXT NOT NULL,
    content_hash   TEXT NOT NULL,
    first_seen_at  TEXT NOT NULL,
    last_seen_at   TEXT NOT NULL,
    collected_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_records_type ON records(record_type);
CREATE INDEX IF NOT EXISTS idx_records_source ON records(source_name);
CREATE INDEX IF NOT EXISTS idx_records_hash ON records(content_hash);

CREATE TABLE IF NOT EXISTS record_revisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id     TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    payload       TEXT NOT NULL,
    observed_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_revisions_record ON record_revisions(record_id);

CREATE TABLE IF NOT EXISTS entity_mappings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_name          TEXT NOT NULL,
    canonical_name    TEXT,
    entity_type       TEXT NOT NULL,
    source_url        TEXT NOT NULL,
    method            TEXT NOT NULL,
    similarity_score  REAL NOT NULL,
    decision          TEXT NOT NULL,
    review_required   INTEGER NOT NULL,
    mapped_at         TEXT NOT NULL,
    notes             TEXT,
    UNIQUE(raw_name, entity_type, source_url)
);
CREATE INDEX IF NOT EXISTS idx_mappings_decision ON entity_mappings(decision);

CREATE TABLE IF NOT EXISTS entity_aliases (
    canonical_name TEXT NOT NULL,
    alias          TEXT NOT NULL,
    source_name    TEXT NOT NULL,
    PRIMARY KEY (canonical_name, alias)
);

CREATE TABLE IF NOT EXISTS source_runs (
    source_name        TEXT PRIMARY KEY,
    source_url         TEXT,
    last_run_at        TEXT,
    last_success_at    TEXT,
    status             TEXT,
    records_discovered INTEGER DEFAULT 0,
    records_accepted   INTEGER DEFAULT 0,
    records_rejected   INTEGER DEFAULT 0,
    error              TEXT
);

CREATE TABLE IF NOT EXISTS checkpoints (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_runs (
    run_id       TEXT PRIMARY KEY,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    status       TEXT NOT NULL,
    summary_json TEXT
);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    def connect(self) -> "Database":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(SCHEMA)
        connection.commit()
        self._connection = connection
        return self

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self.connect()
        assert self._connection is not None
        return self._connection

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def __enter__(self) -> "Database":
        return self.connect()

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self.connection
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    # ------------------------------------------------------------------ #
    # Records
    # ------------------------------------------------------------------ #
    def upsert_record(self, record: dict, *, observed_at: str | None = None) -> str:
        """Insert or update one record. Returns inserted|updated|unchanged."""

        now = observed_at or _utc_now()
        record_id = str(record["record_id"])
        record_type = str(record["recordType"])
        source_name = str(record.get("source", {}).get("name", "unknown"))
        payload = json.dumps(record, ensure_ascii=False, sort_keys=True)
        digest = content_hash(record)

        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT content_hash, payload FROM records WHERE record_id = ?", (record_id,)
            ).fetchone()
            if existing is None:
                connection.execute(
                    """INSERT INTO records
                       (record_id, record_type, source_name, payload, content_hash,
                        first_seen_at, last_seen_at, collected_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (record_id, record_type, source_name, payload, digest, now, now, now),
                )
                return "inserted"
            if existing["content_hash"] == digest:
                connection.execute(
                    "UPDATE records SET last_seen_at = ? WHERE record_id = ?", (now, record_id)
                )
                return "unchanged"
            connection.execute(
                """INSERT INTO record_revisions (record_id, content_hash, payload, observed_at)
                   VALUES (?, ?, ?, ?)""",
                (record_id, existing["content_hash"], existing["payload"], now),
            )
            connection.execute(
                """UPDATE records
                   SET payload = ?, content_hash = ?, source_name = ?, last_seen_at = ?, collected_at = ?
                   WHERE record_id = ?""",
                (payload, digest, source_name, now, now, record_id),
            )
            return "updated"

    def upsert_records(self, records: list[dict], *, observed_at: str | None = None) -> dict[str, int]:
        counts = {"inserted": 0, "updated": 0, "unchanged": 0}
        with self.transaction() as connection:
            for record in records:
                now = observed_at or _utc_now()
                record_id = str(record["record_id"])
                record_type = str(record["recordType"])
                source_name = str(record.get("source", {}).get("name", "unknown"))
                payload = json.dumps(record, ensure_ascii=False, sort_keys=True)
                digest = content_hash(record)
                existing = connection.execute(
                    "SELECT content_hash, payload FROM records WHERE record_id = ?", (record_id,)
                ).fetchone()
                if existing is None:
                    connection.execute(
                        """INSERT INTO records
                           (record_id, record_type, source_name, payload, content_hash,
                            first_seen_at, last_seen_at, collected_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (record_id, record_type, source_name, payload, digest, now, now, now),
                    )
                    counts["inserted"] += 1
                elif existing["content_hash"] == digest:
                    connection.execute(
                        "UPDATE records SET last_seen_at = ? WHERE record_id = ?", (now, record_id)
                    )
                    counts["unchanged"] += 1
                else:
                    connection.execute(
                        """INSERT INTO record_revisions (record_id, content_hash, payload, observed_at)
                           VALUES (?, ?, ?, ?)""",
                        (record_id, existing["content_hash"], existing["payload"], now),
                    )
                    connection.execute(
                        """UPDATE records
                           SET payload = ?, content_hash = ?, source_name = ?, last_seen_at = ?, collected_at = ?
                           WHERE record_id = ?""",
                        (payload, digest, source_name, now, now, record_id),
                    )
                    counts["updated"] += 1
        return counts

    def fetch_records(self, record_type: str | None = None) -> list[dict]:
        query = "SELECT payload FROM records"
        params: tuple[Any, ...] = ()
        if record_type:
            query += " WHERE record_type = ?"
            params = (record_type,)
        query += " ORDER BY record_id"
        rows = self.connection.execute(query, params).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def count_by_type(self) -> dict[str, int]:
        rows = self.connection.execute(
            "SELECT record_type, COUNT(*) AS count FROM records GROUP BY record_type"
        ).fetchall()
        return {row["record_type"]: int(row["count"]) for row in rows}

    def total_records(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) AS count FROM records").fetchone()
        return int(row["count"]) if row else 0

    # ------------------------------------------------------------------ #
    # Entity resolution
    # ------------------------------------------------------------------ #
    def upsert_mapping(self, mapping: EntityMapping | dict) -> None:
        model = mapping if isinstance(mapping, EntityMapping) else EntityMapping.model_validate(mapping)
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO entity_mappings
                   (raw_name, canonical_name, entity_type, source_url, method,
                    similarity_score, decision, review_required, mapped_at, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(raw_name, entity_type, source_url) DO UPDATE SET
                     canonical_name = excluded.canonical_name,
                     method = excluded.method,
                     similarity_score = excluded.similarity_score,
                     decision = excluded.decision,
                     review_required = excluded.review_required,
                     mapped_at = excluded.mapped_at,
                     notes = excluded.notes""",
                (
                    model.raw_name,
                    model.canonical_name,
                    model.entity_type,
                    model.source_url,
                    model.method,
                    model.similarity_score,
                    model.decision,
                    int(model.review_required),
                    model.mapped_at,
                    model.notes,
                ),
            )

    def fetch_mappings(self) -> list[dict]:
        rows = self.connection.execute(
            "SELECT raw_name, canonical_name, entity_type, source_url, method, similarity_score, "
            "decision, review_required, mapped_at, notes FROM entity_mappings ORDER BY id"
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["review_required"] = bool(item["review_required"])
            result.append(item)
        return result

    def count_mappings(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) AS count FROM entity_mappings").fetchone()
        return int(row["count"]) if row else 0

    def add_alias(self, canonical_name: str, alias: str, source_name: str) -> None:
        if not canonical_name or not alias:
            return
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO entity_aliases (canonical_name, alias, source_name)
                   VALUES (?, ?, ?) ON CONFLICT(canonical_name, alias) DO NOTHING""",
                (canonical_name, alias, source_name),
            )

    def fetch_aliases(self) -> dict[str, list[str]]:
        rows = self.connection.execute(
            "SELECT canonical_name, alias FROM entity_aliases ORDER BY canonical_name"
        ).fetchall()
        aliases: dict[str, list[str]] = {}
        for row in rows:
            aliases.setdefault(row["canonical_name"], []).append(row["alias"])
        return aliases

    # ------------------------------------------------------------------ #
    # Source runs, checkpoints, collection runs
    # ------------------------------------------------------------------ #
    def record_source_run(
        self,
        source_name: str,
        *,
        source_url: str | None,
        status: str,
        discovered: int = 0,
        accepted: int = 0,
        rejected: int = 0,
        error: str | None = None,
        ran_at: str | None = None,
    ) -> None:
        now = ran_at or _utc_now()
        success_at = now if status == "ok" else None
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO source_runs
                   (source_name, source_url, last_run_at, last_success_at, status,
                    records_discovered, records_accepted, records_rejected, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source_name) DO UPDATE SET
                     source_url = excluded.source_url,
                     last_run_at = excluded.last_run_at,
                     last_success_at = COALESCE(excluded.last_success_at, source_runs.last_success_at),
                     status = excluded.status,
                     records_discovered = excluded.records_discovered,
                     records_accepted = excluded.records_accepted,
                     records_rejected = excluded.records_rejected,
                     error = excluded.error""",
                (source_name, source_url, now, success_at, status, discovered, accepted, rejected, error),
            )

    def fetch_source_runs(self) -> list[dict]:
        rows = self.connection.execute("SELECT * FROM source_runs ORDER BY source_name").fetchall()
        return [dict(row) for row in rows]

    def set_checkpoint(self, key: str, value: Any) -> None:
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO checkpoints (key, value, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
                (key, json.dumps(value, ensure_ascii=False), _utc_now()),
            )

    def get_checkpoint(self, key: str, default: Any = None) -> Any:
        row = self.connection.execute("SELECT value FROM checkpoints WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return default

    def start_run(self, run_id: str, started_at: str) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO collection_runs (run_id, started_at, status) VALUES (?, ?, 'running')",
                (run_id, started_at),
            )

    def finish_run(self, run_id: str, *, finished_at: str, status: str, summary: dict | None = None) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE collection_runs SET finished_at = ?, status = ?, summary_json = ? WHERE run_id = ?",
                (finished_at, status, json.dumps(summary, ensure_ascii=False) if summary else None, run_id),
            )

    def latest_run(self) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM collection_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        if item.get("summary_json"):
            try:
                item["summary"] = json.loads(item["summary_json"])
            except json.JSONDecodeError:
                item["summary"] = None
        item.pop("summary_json", None)
        return item

    def stats(self) -> dict[str, Any]:
        return {
            "database_path": display_path(self.path),
            "total_records": self.total_records(),
            "records_by_type": self.count_by_type(),
            "entity_mappings": self.count_mappings(),
            "size_bytes": self.path.stat().st_size if self.path.exists() else 0,
        }
