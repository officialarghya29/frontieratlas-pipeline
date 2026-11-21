from __future__ import annotations

import pytest
from pydantic import ValidationError

from frontieratlas.common.text import (
    canonical_url,
    extract_github_urls,
    name_key,
    normalize_name,
)
from frontieratlas.schemas import ProductRecord, StartupRecord, validate_record


def test_url_normalization_strips_tracking_and_trailing_slash():
    url = "HTTPS://WWW.Example.com/Path/?utm_source=x&b=2&a=1#fragment"
    assert canonical_url(url) == "https://example.com/Path?a=1&b=2"


def test_url_normalization_handles_schemeless_input():
    assert canonical_url("example.com/foo/") == "https://example.com/foo"


def test_name_normalization_and_legal_suffix():
    assert normalize_name("Acme, Inc.") == "acme inc"
    assert name_key("Acme, Inc.") == "acme"
    assert name_key("Acme AI LLC") == "acme ai"
    assert name_key("Acme") == "acme"


def test_github_extraction_only_returns_explicit_urls():
    urls = extract_github_urls(
        "Code: https://github.com/owner/repo.git, and https://github.com/other/project.",
        None,
    )
    assert urls == ["https://github.com/owner/repo", "https://github.com/other/project"]
    assert extract_github_urls("No repository is mentioned here.") == []


def _startup() -> dict:
    return {
        "schemaVersion": "1.0",
        "recordType": "STARTUP",
        "record_id": "s1",
        "source": {"name": "YC", "url": "https://example.com/yc.json"},
        "content": {
            "entityName": "Acme AI",
            "data": {"employeeCount": 12},
            "website": "https://acme.example",
            "description": "An AI company.",
            "foundedYear": 2021,
            "industry": "AI",
            "headquarters": "San Francisco",
        },
        "provenance": {"recordUrl": "https://example.com/acme"},
        "collectedAt": "2026-11-21T06:00:00Z",
    }


def test_valid_startup_schema_roundtrip():
    record = validate_record(_startup())
    assert isinstance(record, StartupRecord)
    assert record.content.data.employeeCount == 12


def test_pricing_model_is_restricted():
    with pytest.raises(ValidationError):
        ProductRecord(
            record_id="p1",
            source={"name": "PH", "url": "https://example.com/feed"},
            content={"entityName": "Thing", "pricingModel": "CHEAP"},
            provenance={"recordUrl": "https://example.com/p"},
            collectedAt="2026-11-21T06:00:00Z",
        )


def test_naive_collected_at_is_rejected():
    payload = _startup()
    payload["collectedAt"] = "2026-11-21T06:00:00"
    with pytest.raises(ValidationError):
        validate_record(payload)


def test_unknown_record_type_is_rejected():
    with pytest.raises(ValueError):
        validate_record({"recordType": "ALIEN"})
