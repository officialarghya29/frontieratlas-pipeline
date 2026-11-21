"""GitHub repository enrichment for research papers.

A repository is enriched only when the paper record already contains an
explicit GitHub URL extracted from its abstract, comment, or journal reference.
Repositories are never inferred from paper titles, and star counts are never
fabricated: a failed lookup leaves the count null.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from ..common.config import AppSettings
from ..common.http import AccessBlockedError, AsyncHttpClient, HttpError
from ..common.ids import iso_now
from ..common.logging import get_logger
from ..common.text import canonical_url
from ..storage.db import Database

GITHUB_HOSTS = {"github.com", "www.github.com"}
API_ROOT = "https://api.github.com/repos"


def parse_repository(url: str | None) -> tuple[str, str] | None:
    if not url:
        return None
    try:
        parts = urlsplit(url if "://" in url else f"https://{url}")
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if host not in GITHUB_HOSTS:
        return None
    segments = [segment for segment in parts.path.split("/") if segment]
    if len(segments) < 2:
        return None
    owner, repo = segments[0], segments[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not owner or not repo:
        return None
    return owner, repo


@dataclass
class EnrichmentStats:
    papers_total: int = 0
    papers_with_repo: int = 0
    attempted: int = 0
    enriched: int = 0
    not_found: int = 0
    blocked: int = 0
    failed: int = 0
    already_checked: int = 0
    skipped_limit: int = 0
    errors: list[str] | None = None

    def as_dict(self) -> dict:
        return self.__dict__ | {"errors": (self.errors or [])[:20]}


class GitHubEnricher:
    def __init__(self, settings: AppSettings, client: AsyncHttpClient, db: Database) -> None:
        self.settings = settings
        self.client = client
        self.db = db
        self.log = get_logger("enricher.github")
        self.token = os.environ.get("GITHUB_TOKEN", "").strip()

    async def enrich(self, limit: int | None = None) -> EnrichmentStats:
        stats = EnrichmentStats(errors=[])
        max_repos = limit or 400
        papers = self.db.fetch_records("RESEARCH_PAPER")
        stats.papers_total = len(papers)
        with_repo = [p for p in papers if parse_repository(p["content"].get("github_url"))]
        stats.papers_with_repo = len(with_repo)

        targets = []
        for paper in with_repo:
            if paper["content"].get("github_stars") is not None:
                stats.already_checked += 1
                continue
            targets.append(paper)
        stats.skipped_limit = max(0, len(targets) - max_repos)
        targets = targets[:max_repos]
        stats.attempted = len(targets)

        semaphore = asyncio.Semaphore(4)

        async def enrich_one(paper: dict) -> None:
            parsed = parse_repository(paper["content"].get("github_url"))
            if parsed is None:
                stats.failed += 1
                return
            owner, repo = parsed
            url = f"{API_ROOT}/{owner}/{repo}"
            headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            async with semaphore:
                try:
                    response = await self.client.get(url, headers=headers, retries=2)
                except AccessBlockedError as exc:
                    stats.blocked += 1
                    self._note(stats, f"blocked {owner}/{repo}: {exc.status}")
                    return
                except HttpError as exc:
                    if exc.status == 404:
                        stats.not_found += 1
                        self._note(stats, f"repository not found: {owner}/{repo}")
                    else:
                        stats.failed += 1
                        self._note(stats, f"{owner}/{repo}: HTTP {exc.status}")
                    return
                except Exception as exc:  # noqa: BLE001
                    stats.failed += 1
                    self._note(stats, f"{owner}/{repo}: {type(exc).__name__}: {exc}")
                    return

            try:
                payload = response.json()
                stars = payload.get("stargazers_count")
                if not isinstance(stars, int) or isinstance(stars, bool):
                    raise ValueError("stargazers_count missing from GitHub response")
                if payload.get("full_name", "").lower() != f"{owner}/{repo}".lower():
                    raise ValueError("GitHub response does not match the requested repository")
            except Exception as exc:  # noqa: BLE001
                stats.failed += 1
                self._note(stats, f"{owner}/{repo}: invalid response: {exc}")
                return

            paper["content"]["github_stars"] = stars
            paper["content"]["github_checked_at"] = iso_now()
            paper["content"]["github_url"] = canonical_url(f"https://github.com/{owner}/{repo}")
            self.db.upsert_records([paper])
            stats.enriched += 1

        await asyncio.gather(*(enrich_one(paper) for paper in targets))
        self.log.info(
            "github enrichment finished",
            extra={"count": stats.enriched, "source": "api.github.com"},
        )
        return stats

    @staticmethod
    def _note(stats: EnrichmentStats, message: str) -> None:
        assert stats.errors is not None
        if len(stats.errors) < 50:
            stats.errors.append(message)
