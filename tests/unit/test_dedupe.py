from __future__ import annotations

from frontieratlas.collectors.base import CollectorOutput
from frontieratlas.quality.dedupe import dedupe_key, dedupe_outputs


def _product(name: str, url: str, rid: str) -> dict:
    return {
        "recordType": "PRODUCT",
        "record_id": rid,
        "content": {"entityName": name, "productUrl": url},
        "provenance": {"recordUrl": f"https://news.ycombinator.com/item?id={rid}"},
    }


def test_dedupe_key_normalizes_tracking_parameters():
    assert dedupe_key(_product("A", "https://example.com/p/?utm_source=x", "1")) == dedupe_key(
        _product("A", "https://www.example.com/p", "2")
    )


def test_dedupe_outputs_removes_later_duplicate_and_logs_rejection():
    first = CollectorOutput("showhn", "PRODUCT", discovered=1)
    first.records.append(_product("Alpha", "https://alpha.example", "1"))
    second = CollectorOutput("huggingface_spaces", "PRODUCT", discovered=2)
    second.records.append(_product("Alpha mirror", "https://www.alpha.example/", "2"))
    second.records.append(_product("Beta", "https://beta.example", "3"))

    removed = dedupe_outputs([first, second])
    assert removed == 1
    assert len(first.records) == 1
    assert len(second.records) == 1
    assert second.records[0]["content"]["entityName"] == "Beta"
    assert any(rejection.reason == "duplicate_across_sources" for rejection in second.rejections)
