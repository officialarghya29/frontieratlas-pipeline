"""Product Hunt public Atom feed collector (no authenticated API required)."""

from __future__ import annotations

from urllib.parse import urlsplit

import feedparser
from bs4 import BeautifulSoup

from ..common.ids import iso_now
from ..common.keywords import is_ai_related
from ..common.text import canonical_url, collapse_whitespace, normalize_name, stable_id, truncate
from ..schemas import ProductRecord, validate_record
from .base import BaseCollector, CollectorContext, CollectorOutput


def _feed_description(entry: dict) -> str | None:
    content = entry.get("content") or []
    if content and isinstance(content, list):
        raw = content[0].get("value") or ""
        if raw:
            soup = BeautifulSoup(raw, "html.parser")
            paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
            for paragraph in paragraphs:
                cleaned = collapse_whitespace(paragraph)
                if cleaned and "discussion" not in cleaned.lower() and "link" != cleaned.lower():
                    return truncate(cleaned, 1500)
    return truncate(collapse_whitespace(BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" ", strip=True)), 1500)


class ProductHuntCollector(BaseCollector):
    name = "producthunt"
    record_type = "PRODUCT"

    def __init__(self, source_cfg: dict) -> None:
        super().__init__()
        self.cfg = source_cfg
        self.source_url = str(source_cfg.get("url", "https://www.producthunt.com/feed"))
        self.fallback_url = "https://www.producthunt.com/feed"
        self.source_meta = {
            "source_name": source_cfg.get("name", "Product Hunt (Atom feed)"),
            "source_url": self.source_url,
            "access_method": "public Atom feed",
            "authentication": "none",
            "terms_url": source_cfg.get("terms_url"),
            "rate_limit": source_cfg.get("rate_limit"),
            "parser": "atom_feed",
            "date_semantics": source_cfg.get("date_semantics"),
        }

    async def collect(self, ctx: CollectorContext) -> CollectorOutput:
        output = CollectorOutput(self.name, self.record_type, source_meta=self.source_meta)
        response = await ctx.client.get(self.source_url, raw_label="feed")
        feed = feedparser.parse(response.body)
        entries = feed.entries
        if not entries and self.source_url != self.fallback_url:
            response = await ctx.client.get(self.fallback_url, raw_label="feed-fallback")
            feed = feedparser.parse(response.body)
            entries = feed.entries
            output.notes.append("Category feed returned no entries; fell back to the public Product Hunt feed.")

        output.discovered = len(entries)
        seen_urls: set[str] = set()
        seen_names: set[str] = set()

        for entry in entries:
            title = collapse_whitespace(entry.get("title"))
            link = canonical_url(entry.get("link"))
            description = _feed_description(entry)
            if not title or not link:
                output.add_rejection("missing_identity", title, link)
                continue
            if not is_ai_related(f"{title} {description or ''}"):
                output.add_rejection("not_ai_related", title, link)
                continue
            if link in seen_urls or normalize_name(title) in seen_names:
                output.add_rejection("duplicate_in_source", title, link)
                continue

            slug = urlsplit(link).path.rstrip("/").rsplit("/", 1)[-1]
            try:
                record = ProductRecord(
                    record_id=stable_id("PRODUCT", "producthunt", slug),
                    source={"name": self.source_meta["source_name"], "url": self.source_url},
                    content={
                        "entityName": title,
                        "startupName": None,
                        "pricingModel": "UNKNOWN",
                        "productUrl": link,
                        "description": description,
                        "category": "Product Hunt launch",
                    },
                    provenance={"recordUrl": link},
                    collectedAt=iso_now(ctx.now),
                ).model_dump(mode="json")
                validate_record(record)
            except Exception as exc:  # noqa: BLE001
                output.add_rejection("schema_validation_failed", f"{title}: {exc}", link)
                continue

            output.records.append(record)
            seen_urls.add(link)
            seen_names.add(normalize_name(title))

        output.notes.append(f"Product Hunt feed entries={output.discovered}; accepted={output.accepted}.")
        return output
