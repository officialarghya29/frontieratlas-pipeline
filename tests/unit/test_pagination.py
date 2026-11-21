from __future__ import annotations

from datetime import datetime, timezone

from frontieratlas.collectors.base import CollectorContext
from frontieratlas.collectors.hfspaces import HuggingFaceSpacesCollector
from frontieratlas.collectors.jobs import HimalayasCollector
from frontieratlas.common.config import get_settings
from frontieratlas.storage.db import Database

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


class FakeAPIClient:
    def __init__(self, pages: dict[int, list[dict]]):
        self.pages = pages
        self.calls: list[dict] = []

    async def get_json(self, url, *, params=None, raw_label=None, **kwargs):
        self.calls.append(dict(params or {}))
        skip = int((params or {}).get("skip", 0))
        return self.pages.get(skip, [])


async def test_huggingface_pagination(tmp_path):
    pages = {
        0: [
            {"id": "org/one", "private": False, "cardData": {"title": "One", "short_description": "First app"}},
            {"id": "org/two", "private": False, "cardData": {"title": "Two", "short_description": "Second app"}},
        ],
        2: [
            {"id": "org/three", "private": False, "cardData": {"title": "Three"}},
        ],
    }
    collector = HuggingFaceSpacesCollector(
        {"name": "Hugging Face Spaces", "url": "https://huggingface.co/api/spaces", "page_size": 2, "max_pages": 3}
    )
    db = Database(tmp_path / "test.db").connect()
    ctx = CollectorContext(settings=get_settings(), client=FakeAPIClient(pages), db=db, now=NOW)  # type: ignore[arg-type]
    output = await collector.collect(ctx)
    assert output.discovered == 3
    assert output.accepted == 2
    assert output.rejected == 1
    assert any(rejection.reason == "missing_description" for rejection in output.rejections)


def _himalayas_job(job_id: str, epoch: int) -> dict:
    return {
        "title": "AI Engineer",
        "companyName": "Acme",
        "guid": f"https://himalayas.example/jobs/{job_id}",
        "pubDate": str(epoch),
        "categories": ["AI"],
    }


class FakeCursorClient:
    def __init__(self, pages: list[dict]):
        self.pages = pages
        self.calls: list[dict] = []

    async def get_json(self, url, *, params=None, raw_label=None, **kwargs):
        self.calls.append(dict(params or {}))
        return self.pages.pop(0)


async def test_himalayas_cursor_pagination(tmp_path):
    fresh_epoch = int(NOW.timestamp()) - 3600
    pages = [
        {"jobs": [_himalayas_job("1", fresh_epoch), _himalayas_job("2", fresh_epoch)], "nextCursor": "abc"},
        {"jobs": [_himalayas_job("3", fresh_epoch)], "nextCursor": None},
    ]
    collector = HimalayasCollector(
        {
            "key": "himalayas",
            "name": "Himalayas",
            "url": "https://himalayas.app/jobs/api",
            "date_field": "pubDate",
            "request_limit": 20,
            "pages": 3,
        }
    )
    db = Database(tmp_path / "test.db").connect()
    client = FakeCursorClient(pages)
    ctx = CollectorContext(settings=get_settings(), client=client, db=db, now=NOW)  # type: ignore[arg-type]
    output = await collector.collect(ctx)
    assert output.accepted == 3
    assert len(client.calls) == 2
    assert client.calls[1].get("cursor") == "abc"
    assert all(record["content"]["date"] == "2026-11-21T11:00:00Z" for record in output.records)
