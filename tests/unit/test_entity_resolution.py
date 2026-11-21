from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from frontieratlas.common.config import get_settings
from frontieratlas.resolvers.entities import EntityResolver
from frontieratlas.storage.db import Database


def _startup(name: str, website: str | None, rid: str) -> dict:
    return {
        "schemaVersion": "1.0",
        "recordType": "STARTUP",
        "record_id": rid,
        "source": {"name": "YC", "url": "https://example.com/yc.json"},
        "content": {"entityName": name, "data": {"employeeCount": None}, "website": website},
        "provenance": {"recordUrl": f"https://example.com/{rid}"},
        "collectedAt": "2026-11-21T06:00:00Z",
    }


def _product(name: str, url: str, rid: str) -> dict:
    return {
        "schemaVersion": "1.0",
        "recordType": "PRODUCT",
        "record_id": rid,
        "source": {"name": "Show HN", "url": "https://hn.algolia.com/api/v1/search"},
        "content": {"entityName": name, "pricingModel": "UNKNOWN", "productUrl": url},
        "provenance": {"recordUrl": f"https://news.ycombinator.com/item?id={rid}"},
        "collectedAt": "2026-11-21T06:00:00Z",
    }


def _resolver(tmp_path):
    db = Database(tmp_path / "test.db").connect()
    db.upsert_records(
        [
            _startup("Acme AI", "https://acme.example", "s1"),
            _startup("Globex", "https://globex.example", "s2"),
        ]
    )
    db.add_alias("Acme AI", "Acme Corporation", "yc_ai")
    settings = get_settings()
    return db, EntityResolver(settings.entity_resolution, db)


def test_exact_match(tmp_path):
    db, resolver = _resolver(tmp_path)
    mapping = resolver.resolve("Acme AI", "https://unrelated.example")
    assert mapping.decision == "AUTO_MATCHED"
    assert mapping.method == "exact_name"
    assert mapping.canonical_name == "Acme AI"
    assert mapping.similarity_score == 100


def test_alias_match(tmp_path):
    db, resolver = _resolver(tmp_path)
    mapping = resolver.resolve("Acme Corporation", "https://unrelated.example")
    assert mapping.method == "alias_match"
    assert mapping.decision == "AUTO_MATCHED"


def test_domain_match_is_verified_evidence(tmp_path):
    db, resolver = _resolver(tmp_path)
    mapping = resolver.resolve("Totally Different Name", "https://www.globex.example/product")
    assert mapping.method == "domain_match"
    assert mapping.canonical_name == "Globex"
    assert mapping.decision == "AUTO_MATCHED"


def test_fuzzy_ambiguous_requires_review(tmp_path):
    db, resolver = _resolver(tmp_path)
    strict = replace(get_settings().entity_resolution, auto_merge_threshold=101, review_threshold=60)
    resolver.settings = strict
    mapping = resolver.resolve("Acme AI Labs", "https://unrelated.example")
    assert mapping.method == "fuzzy_token_set"
    assert mapping.decision == "REVIEW_REQUIRED"
    assert mapping.review_required is True


def test_no_match_keeps_null_canonical(tmp_path):
    db, resolver = _resolver(tmp_path)
    mapping = resolver.resolve("Zzz Quantum Widget", "https://zzz.example")
    assert mapping.decision == "NO_MATCH"
    assert mapping.canonical_name is None
    assert mapping.review_required is False


def test_seed_only_match_requires_review(tmp_path):
    db, resolver = _resolver(tmp_path)
    mapping = resolver.resolve("OpenAI", "https://openai.example")
    assert mapping.method == "seed_exact"
    assert mapping.decision == "REVIEW_REQUIRED"


def test_shared_app_store_domain_never_matches(tmp_path):
    db = Database(tmp_path / "test.db").connect()
    db.upsert_records([
        _startup(
            "Evie",
            "https://apps.apple.com/us/app/evie/id6761323087",
            "s1",
        )
    ])
    resolver = EntityResolver(get_settings().entity_resolution, db)
    mapping = resolver.resolve("Call Nara - AI voice companion", "https://apps.apple.com/us/app/call-nara/id6794990805")
    assert mapping.method != "domain_match"
    assert mapping.decision == "NO_MATCH"


def test_descriptive_title_is_not_fuzzy_matched(tmp_path):
    db, resolver = _resolver(tmp_path)
    mapping = resolver.resolve(
        "Halo - A Personal AI with On-Device Harness for Your Agents",
        "https://halo.example",
    )
    assert mapping.method == "not_name_like"
    assert mapping.decision == "NO_MATCH"


def test_product_resolution_persists_mapping_rows(tmp_path):
    db, resolver = _resolver(tmp_path)
    db.upsert_records([_product("Acme AI", "https://acme.example/app", "p1")])
    stats = resolver.resolve_products()
    assert stats.products_total == 1
    assert stats.auto_matched == 1
    assert db.count_mappings() == 1
    product = db.fetch_records("PRODUCT")[0]
    assert product["content"]["startupName"] == "Acme AI"
