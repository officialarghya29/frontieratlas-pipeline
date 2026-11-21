from __future__ import annotations

import json
from datetime import datetime, timezone

from frontieratlas.common.text import content_hash
from frontieratlas.schemas import EntityMapping
from frontieratlas.storage.db import Database


def _record(description: str = "first") -> dict:
    return {
        "schemaVersion": "1.0",
        "recordType": "STARTUP",
        "record_id": "s1",
        "source": {"name": "YC", "url": "https://example.com/yc.json"},
        "content": {"entityName": "Acme", "data": {"employeeCount": 1}, "description": description},
        "provenance": {"recordUrl": "https://example.com/acme"},
        "collectedAt": "2026-11-21T06:00:00Z",
    }


def test_upsert_is_idempotent(tmp_path):
    with Database(tmp_path / "test.db") as db:
        assert db.upsert_record(_record()) == "inserted"
        assert db.upsert_record(_record()) == "unchanged"
        assert db.total_records() == 1


def test_upsert_tracks_revision_without_duplicate_row(tmp_path):
    with Database(tmp_path / "test.db") as db:
        db.upsert_record(_record("first"))
        assert db.upsert_record(_record("second")) == "updated"
        assert db.total_records() == 1
        rows = db.connection.execute("SELECT COUNT(*) AS c FROM record_revisions").fetchone()
        assert rows["c"] == 1
        revision = db.connection.execute(
            "SELECT content_hash, payload FROM record_revisions"
        ).fetchone()
        assert revision["content_hash"] == content_hash(_record("first"))
        assert json.loads(revision["payload"])["content"]["description"] == "first"
        assert db.fetch_records("STARTUP")[0]["content"]["description"] == "second"


def test_entity_mapping_upsert_is_idempotent(tmp_path):
    with Database(tmp_path / "test.db") as db:
        mapping = {
            "raw_name": "Acme",
            "canonical_name": "Acme",
            "entity_type": "PRODUCT",
            "source_url": "https://example.com/acme",
            "method": "exact_name",
            "similarity_score": 100,
            "decision": "AUTO_MATCHED",
            "review_required": False,
            "mapped_at": "2026-11-21T06:00:00Z",
        }
        db.upsert_mapping(mapping)
        mapping["decision"] = "REVIEW_REQUIRED"
        mapping["review_required"] = True
        db.upsert_mapping(mapping)
        assert db.count_mappings() == 1
        assert db.fetch_mappings()[0]["review_required"] is True


def test_checkpoints_roundtrip(tmp_path):
    with Database(tmp_path / "test.db") as db:
        db.set_checkpoint("arxiv:cs.AI", 400)
        assert db.get_checkpoint("arxiv:cs.AI") == 400
        assert db.get_checkpoint("missing", "fallback") == "fallback"
