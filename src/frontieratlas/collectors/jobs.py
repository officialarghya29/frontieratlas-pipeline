"""AI/technology job collectors for five public job-board APIs.

Only listings whose public publication timestamp falls inside the strict
24-hour window are accepted. Remote boards are marked remote from the board's
own semantics, never guessed from the job text.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Iterable

from ..common.ids import iso_now
from ..common.keywords import JOB_AI_KEYWORDS, classify_role, is_ai_related
from ..common.text import canonical_url, collapse_whitespace, stable_id, strip_html, truncate
from ..common.timeutil import TimestampError, iso_utc, parse_timestamp
from ..schemas import JobRecord, validate_record
from .base import BaseCollector, CollectorContext, CollectorOutput


def _field(job: dict, *names: str) -> Any:
    for name in names:
        value = job.get(name)
        if value not in (None, ""):
            return value
    return None


class JobBoardCollector(BaseCollector):
    record_type = "JOB"

    def __init__(self, source_cfg: dict) -> None:
        self.cfg = source_cfg
        self.name = str(source_cfg["key"])
        super().__init__()
        self.board_url = str(source_cfg["url"])
        self.source_url = self.board_url
        self.date_field = str(source_cfg.get("date_field", "pubDate"))
        self.request_limit = int(source_cfg.get("request_limit", 100))
        self.pages = int(source_cfg.get("pages", 1))
        self.source_meta = {
            "source_name": source_cfg.get("name", self.name),
            "source_url": self.board_url,
            "access_method": source_cfg.get("access_method"),
            "authentication": "none",
            "terms_url": source_cfg.get("terms_url"),
            "rate_limit": "1 request/second enforced client-side",
            "parser": source_cfg.get("parser", self.name),
            "date_semantics": f"publication timestamp from field '{self.date_field}'; crawl time is never substituted",
        }

    async def collect(self, ctx: CollectorContext) -> CollectorOutput:
        output = CollectorOutput(self.name, self.record_type, source_meta=self.source_meta)
        candidates = await self._fetch_candidates(ctx, output)
        output.discovered = len(candidates)
        seen_urls: set[str] = set()

        for job in candidates:
            self._parse_job(job, ctx, output, seen_urls)

        output.notes.append(
            f"{self.name}: {output.discovered} raw listings, {output.accepted} AI/tech listings within "
            f"{ctx.max_age_hours}h."
        )
        return output

    async def _fetch_candidates(self, ctx: CollectorContext, output: CollectorOutput) -> list[dict]:
        raise NotImplementedError

    def _parse_job(
        self,
        job: dict,
        ctx: CollectorContext,
        output: CollectorOutput,
        seen_urls: set[str],
    ) -> None:
        if not isinstance(job, dict):
            output.add_rejection("invalid_record", "listing is not an object", self.board_url)
            return

        title = collapse_whitespace(str(_field(job, "title", "position", "jobTitle") or ""))
        company = collapse_whitespace(str(_field(job, "company", "companyName", "company_name") or ""))
        raw_url = _field(job, "url", "jobUrl", "job_url", "application_url", "applicationLink", "guid")
        url = canonical_url(str(raw_url)) if raw_url else None
        if not title or not company or not url:
            output.add_rejection("missing_identity", title or company or None, url)
            return

        raw_date = _field(job, self.date_field, "pubDate", "publication_date", "date", "created_at", "epoch")
        if raw_date in (None, ""):
            output.add_rejection("missing_publication_date", f"{company} — {title}", url)
            return
        try:
            published = parse_timestamp(raw_date)
        except TimestampError as exc:
            output.add_rejection("invalid_publication_date", f"{company} — {title}: {exc}", url)
            return

        if published > ctx.now + timedelta(minutes=ctx.clock_skew_minutes):
            output.add_rejection("future_publication_timestamp", f"{company} — {title}", url)
            return
        if published < ctx.now - timedelta(hours=ctx.max_age_hours):
            output.add_rejection("stale_publication_timestamp", f"{company} — {title}", url)
            return

        description = strip_html(str(_field(job, "description", "jobDescription", "excerpt") or ""))
        tags = _field(job, "tags", "categories", "parentCategories", "jobIndustry", "jobLevel") or []
        if isinstance(tags, list):
            tags_text = " ".join(str(tag) for tag in tags)
        else:
            tags_text = str(tags)
        relevance_text = f"{title} {tags_text} {truncate(description, 3000) or ''}"
        if not is_ai_related(relevance_text, JOB_AI_KEYWORDS):
            output.add_rejection("not_ai_related", f"{company} — {title}", url)
            return

        if url in seen_urls:
            output.add_rejection("duplicate_in_source", f"{company} — {title}", url)
            return

        try:
            record = JobRecord(
                record_id=stable_id("JOB", self.name, url),
                source={"name": self.source_meta["source_name"], "url": self.board_url},
                content={
                    "company": company,
                    "date": iso_utc(published),
                    "is_remote": self._is_remote(job),
                    "role_family": classify_role(title),
                    "title": title,
                    "job_url": url,
                },
                provenance={
                    "recordUrl": url,
                    "dateEvidence": f"{self.name} field '{self.date_field}' (timezone-aware)",
                },
                freshness_verified=True,
                collectedAt=iso_now(ctx.now),
            ).model_dump(mode="json")
            validate_record(record)
        except Exception as exc:  # noqa: BLE001
            output.add_rejection("schema_validation_failed", f"{company} — {title}: {exc}", url)
            return

        seen_urls.add(url)
        output.records.append(record)

    def _is_remote(self, job: dict) -> bool:
        return True


class HimalayasCollector(JobBoardCollector):
    async def _fetch_candidates(self, ctx: CollectorContext, output: CollectorOutput) -> list[dict]:
        results: list[dict] = []
        cursor: str | None = None
        for _ in range(self.pages):
            params: dict[str, Any] = {"limit": self.request_limit}
            if cursor:
                params["cursor"] = cursor
            payload = await ctx.client.get_json(self.board_url, params=params, raw_label="jobs")
            if not isinstance(payload, dict):
                break
            jobs = payload.get("jobs") or []
            results.extend(jobs)
            cursor = payload.get("nextCursor")
            if not cursor:
                break
        return results


class RemotiveCollector(JobBoardCollector):
    async def _fetch_candidates(self, ctx: CollectorContext, output: CollectorOutput) -> list[dict]:
        payload = await ctx.client.get_json(
            self.board_url, params={"limit": self.request_limit}, raw_label="jobs"
        )
        if isinstance(payload, dict):
            return payload.get("jobs") or []
        return []


class RemoteOKCollector(JobBoardCollector):
    async def _fetch_candidates(self, ctx: CollectorContext, output: CollectorOutput) -> list[dict]:
        payload = await ctx.client.get_json(self.board_url, raw_label="jobs")
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict) and item.get("position")]


class ArbeitnowCollector(JobBoardCollector):
    async def _fetch_candidates(self, ctx: CollectorContext, output: CollectorOutput) -> list[dict]:
        payload = await ctx.client.get_json(self.board_url, raw_label="jobs")
        if isinstance(payload, dict):
            return payload.get("data") or []
        return []

    def _is_remote(self, job: dict) -> bool:
        return bool(job.get("remote"))


class JobicyCollector(JobBoardCollector):
    async def _fetch_candidates(self, ctx: CollectorContext, output: CollectorOutput) -> list[dict]:
        payload = await ctx.client.get_json(
            self.board_url, params={"count": self.request_limit}, raw_label="jobs"
        )
        if isinstance(payload, dict):
            return payload.get("jobs") or []
        return []
