"""RSS news collector with strict 24-hour publication verification.

Full text is fetched only from the public article page and only when it is
freely available. A paywall, login wall, 403, or short body is never bypassed;
the record then keeps the RSS summary and is explicitly labelled SUMMARY_ONLY.
"""

from __future__ import annotations

import feedparser
from bs4 import BeautifulSoup

from ..common.http import HttpError
from ..common.ids import iso_now
from ..common.text import canonical_url, collapse_whitespace, stable_id, strip_html, truncate
from ..common.timeutil import TimestampError, iso_utc, parse_timestamp
from ..schemas import NewsRecord, validate_record
from .base import BaseCollector, CollectorContext, CollectorOutput

MIN_FULL_TEXT_CHARS = 600


def extract_article_text(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()
    container = soup.find("article") or soup.find("main") or soup.body
    if container is None:
        return None
    paragraphs = []
    for node in container.find_all("p"):
        text = collapse_whitespace(node.get_text(" ", strip=True))
        if text and len(text) >= 40:
            paragraphs.append(text)
    body = " ".join(paragraphs)
    return truncate(body, 20000) if len(body) >= MIN_FULL_TEXT_CHARS else None


class NewsSourceCollector(BaseCollector):
    record_type = "NEWS"

    def __init__(self, source_cfg: dict) -> None:
        self.cfg = source_cfg
        self.name = str(source_cfg["key"])
        super().__init__()
        self.feed_url = str(source_cfg["feed_url"])
        self.source_url = self.feed_url
        self.publisher = str(source_cfg.get("publisher") or source_cfg.get("name") or self.name)
        self.source_meta = {
            "source_name": source_cfg.get("name", self.name),
            "source_url": self.feed_url,
            "access_method": "RSS",
            "authentication": "none",
            "terms_url": source_cfg.get("terms_url"),
            "rate_limit": "single feed fetch per run",
            "parser": "rss_feed",
            "date_semantics": "RSS <published> field, timezone-aware; <updated> is never used for freshness",
        }

    async def collect(self, ctx: CollectorContext) -> CollectorOutput:
        output = CollectorOutput(self.name, self.record_type, source_meta=self.source_meta)
        response = await ctx.client.get(self.feed_url, raw_label="feed")
        feed = feedparser.parse(response.body)
        if getattr(feed, "bozo", 0) and not feed.entries:
            raise ValueError(f"feed could not be parsed: {getattr(feed, 'bozo_exception', 'unknown')}")

        output.discovered = len(feed.entries)
        seen: set[str] = set()

        for entry in feed.entries:
            title = collapse_whitespace(entry.get("title"))
            link = canonical_url(entry.get("link"))
            if not title or not link:
                output.add_rejection("missing_identity", title, link)
                continue
            if link in seen:
                output.add_rejection("duplicate_in_source", title, link)
                continue

            raw_date = entry.get("published")
            if not raw_date:
                output.add_rejection(
                    "missing_publication_date",
                    f"{title}: feed has no <published> field; <updated> is not accepted as publication time",
                    link,
                )
                continue
            try:
                published = parse_timestamp(raw_date)
            except TimestampError as exc:
                output.add_rejection("invalid_publication_date", f"{title}: {exc}", link)
                continue

            cutoff_ok = True
            from datetime import timedelta

            if published > ctx.now + timedelta(minutes=ctx.clock_skew_minutes):
                output.add_rejection("future_publication_timestamp", f"{title}: {iso_utc(published)}", link)
                cutoff_ok = False
            elif published < ctx.now - timedelta(hours=ctx.max_age_hours):
                output.add_rejection("stale_publication_timestamp", f"{title}: {iso_utc(published)}", link)
                cutoff_ok = False
            if not cutoff_ok:
                continue

            summary = truncate(strip_html(entry.get("summary")), 3000)
            full_text = None
            extraction_status = "SUMMARY_ONLY"
            try:
                article = await ctx.client.get(link, retries=0)
                if article.status == 200 and "html" in article.headers.get("content-type", ""):
                    full_text = extract_article_text(article.text())
                    if full_text:
                        extraction_status = "FULL_TEXT"
            except (HttpError, Exception) as exc:  # noqa: BLE001 - fallback is summary, never failure
                output.notes.append(f"Full-text fetch unavailable for {link}: {type(exc).__name__}")

            try:
                record = NewsRecord(
                    record_id=stable_id("NEWS", "article", link),
                    source={"name": self.publisher, "url": self.feed_url},
                    content={
                        "title": title,
                        "date": iso_utc(published),
                        "publisher": self.publisher,
                        "full_text": full_text,
                        "summary": summary,
                        "article_url": link,
                    },
                    provenance={
                        "recordUrl": link,
                        "dateEvidence": "RSS published field (timezone-aware)",
                    },
                    freshness_verified=True,
                    extraction_status=extraction_status,
                    collectedAt=iso_now(ctx.now),
                ).model_dump(mode="json")
                validate_record(record)
            except Exception as exc:  # noqa: BLE001
                output.add_rejection("schema_validation_failed", f"{title}: {exc}", link)
                continue

            seen.add(link)
            output.records.append(record)

        output.notes.append(
            f"{self.publisher}: {output.discovered} feed entries, {output.accepted} within the last "
            f"{ctx.max_age_hours}h, {sum(1 for r in output.records if r['extraction_status'] == 'FULL_TEXT')} full-text."
        )
        return output
