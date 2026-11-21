from __future__ import annotations

import json

from frontieratlas.common.config import get_settings
from frontieratlas.common.http import HttpError, HttpResponse
from frontieratlas.enrichers.github import GitHubEnricher, parse_repository
from frontieratlas.storage.db import Database


class FakeGitHubClient:
    def __init__(self, responses: dict[str, tuple[int, dict]]):
        self.responses = responses
        self.calls: list[str] = []

    async def get(self, url: str, *, headers=None, retries=None, **kwargs):
        self.calls.append(url)
        status, body = self.responses[url]
        if status >= 400:
            raise HttpError(url, status, "error")
        return HttpResponse(url=url, status=status, headers={"content-type": "application/json"}, body=json.dumps(body).encode())


def _paper(github_url: str, rid: str = "2401.00001") -> dict:
    return {
        "schemaVersion": "1.0",
        "recordType": "RESEARCH_PAPER",
        "record_id": rid,
        "source": {"name": "arXiv", "url": "https://export.arxiv.org/api/query"},
        "content": {
            "title": "A Paper",
            "authors": ["A. Author"],
            "paper_url": f"https://arxiv.org/abs/{rid}",
            "github_url": github_url,
            "github_stars": None,
            "github_checked_at": None,
            "published_date": "2026-11-20T00:00:00Z",
            "abstract": "Abstract.",
        },
        "provenance": {"recordUrl": f"https://arxiv.org/abs/{rid}", "githubEvidenceUrl": f"https://arxiv.org/abs/{rid}"},
        "collectedAt": "2026-11-21T06:00:00Z",
    }


def test_parse_repository_variants():
    assert parse_repository("https://github.com/owner/repo") == ("owner", "repo")
    assert parse_repository("https://github.com/owner/repo.git") == ("owner", "repo")
    assert parse_repository("https://github.com/owner/repo/tree/main/src") == ("owner", "repo")
    assert parse_repository("https://gitlab.com/owner/repo") is None
    assert parse_repository("https://github.com/owner") is None
    assert parse_repository(None) is None


async def test_enrichment_sets_stars_and_timestamp(tmp_path):
    db = Database(tmp_path / "test.db").connect()
    db.upsert_records([_paper("https://github.com/owner/repo")])
    url = "https://api.github.com/repos/owner/repo"
    client = FakeGitHubClient({url: (200, {"full_name": "owner/repo", "stargazers_count": 1234})})
    enricher = GitHubEnricher(get_settings(), client, db)  # type: ignore[arg-type]
    stats = await enricher.enrich(limit=10)
    assert stats.enriched == 1
    record = db.fetch_records("RESEARCH_PAPER")[0]
    assert record["content"]["github_stars"] == 1234
    assert record["content"]["github_checked_at"].endswith("Z")
    db.close()


async def test_missing_repository_keeps_stars_null(tmp_path):
    db = Database(tmp_path / "test.db").connect()
    db.upsert_records([_paper("https://github.com/owner/missing")])
    url = "https://api.github.com/repos/owner/missing"
    client = FakeGitHubClient({url: (404, {})})
    enricher = GitHubEnricher(get_settings(), client, db)  # type: ignore[arg-type]
    stats = await enricher.enrich(limit=10)
    assert stats.not_found == 1
    record = db.fetch_records("RESEARCH_PAPER")[0]
    assert record["content"]["github_stars"] is None
    db.close()
