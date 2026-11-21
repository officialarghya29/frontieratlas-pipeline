"""arXiv research-paper collector with explicit GitHub-link evidence only."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from ..common.timeutil import TimestampError, iso_utc, parse_timestamp
from ..common.text import collapse_whitespace, extract_github_urls, stable_id, truncate
from ..schemas import ResearchPaperRecord, validate_record
from .base import BaseCollector, CollectorContext, CollectorOutput

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"

_VERSION_RE = re.compile(r"v\d+$")


def _entry_id(raw_id: str) -> str | None:
    if not raw_id:
        return None
    identifier = raw_id.rsplit("/", 1)[-1].strip()
    identifier = _VERSION_RE.sub("", identifier)
    return identifier or None


class ArxivCollector(BaseCollector):
    name = "arxiv"
    record_type = "RESEARCH_PAPER"

    def __init__(self, source_cfg: dict) -> None:
        super().__init__()
        self.cfg = source_cfg
        self.source_url = str(source_cfg.get("url", "https://export.arxiv.org/api/query"))
        self.categories = list(source_cfg.get("categories") or ["cs.AI"])
        self.batch_size = int(source_cfg.get("batch_size", 200))
        self.max_per_category = int(source_cfg.get("max_results_per_category", 320))
        self.source_meta = {
            "source_name": source_cfg.get("name", "arXiv"),
            "source_url": self.source_url,
            "access_method": source_cfg.get("access_method", "public Atom API"),
            "authentication": source_cfg.get("authentication", "none"),
            "terms_url": source_cfg.get("terms_url"),
            "rate_limit": source_cfg.get("rate_limit"),
            "parser": "arxiv_atom",
            "date_semantics": source_cfg.get("date_semantics"),
        }

    async def collect(self, ctx: CollectorContext) -> CollectorOutput:
        output = CollectorOutput(self.name, self.record_type, source_meta=self.source_meta)
        seen: set[str] = set()

        for category in self.categories:
            start = 0
            fetched_this_category = 0
            while fetched_this_category < self.max_per_category:
                remaining = self.max_per_category - fetched_this_category
                limit = min(self.batch_size, remaining)
                params = {
                    "search_query": f"cat:{category}",
                    "start": start,
                    "max_results": limit,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                }
                response = await ctx.client.get(
                    self.source_url,
                    params=params,
                    raw_label=f"{category.replace('.', '_')}-{start}",
                )
                try:
                    root = ET.fromstring(response.body)
                except ET.ParseError as exc:
                    output.notes.append(f"{category}: parse error at start={start}: {exc}")
                    break

                entries = root.findall(f"{ATOM}entry")
                if not entries:
                    break
                output.discovered += len(entries)
                fetched_this_category += len(entries)

                for entry in entries:
                    self._parse_entry(entry, ctx, output, seen)

                if len(entries) < limit:
                    break
                start += len(entries)

        output.notes.append(
            f"arXiv categories={self.categories}; discovered={output.discovered}; unique accepted={output.accepted}."
        )
        return output

    def _parse_entry(
        self,
        entry: ET.Element,
        ctx: CollectorContext,
        output: CollectorOutput,
        seen: set[str],
    ) -> None:
        raw_id = (entry.findtext(f"{ATOM}id") or "").strip()
        paper_id = _entry_id(raw_id)
        title = collapse_whitespace(entry.findtext(f"{ATOM}title"))
        if not paper_id or not title:
            output.add_rejection("missing_identity", raw_id or title, raw_id or self.source_url)
            return
        if paper_id in seen:
            output.add_rejection("duplicate_in_source", paper_id, raw_id)
            return

        published = entry.findtext(f"{ATOM}published")
        try:
            published_iso = iso_utc(parse_timestamp(published))
        except TimestampError as exc:
            output.add_rejection("invalid_publication_date", f"{paper_id}: {exc}", raw_id)
            return

        authors = [
            collapse_whitespace(author.findtext(f"{ATOM}name")) or ""
            for author in entry.findall(f"{ATOM}author")
        ]
        authors = [name for name in authors if name]
        abstract = truncate(collapse_whitespace(entry.findtext(f"{ATOM}summary")), 8000)
        comment = entry.findtext(f"{ARXIV}comment") or ""
        journal_ref = entry.findtext(f"{ARXIV}journal_ref") or ""

        github_urls = extract_github_urls(abstract, comment, journal_ref)
        github_url = github_urls[0] if github_urls else None
        paper_url = f"https://arxiv.org/abs/{paper_id}"

        try:
            record = ResearchPaperRecord(
                record_id=paper_id,
                source={"name": "arXiv", "url": self.source_url},
                content={
                    "title": title,
                    "authors": authors,
                    "paper_url": paper_url,
                    "github_url": github_url,
                    "github_stars": None,
                    "github_checked_at": None,
                    "published_date": published_iso,
                    "abstract": abstract,
                },
                provenance={
                    "recordUrl": paper_url,
                    "githubEvidenceUrl": paper_url if github_url else None,
                },
                collectedAt=iso_utc(ctx.now),
            ).model_dump(mode="json")
            validate_record(record)
        except Exception as exc:  # noqa: BLE001 - per-record isolation
            output.add_rejection("schema_validation_failed", f"{paper_id}: {exc}", paper_url)
            return

        seen.add(paper_id)
        output.records.append(record)
