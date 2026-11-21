"""Hacker News "Show HN" launch collector using the public Algolia Search API."""

from __future__ import annotations

import re

from ..common.ids import iso_now
from ..common.keywords import is_ai_related
from ..common.text import (
    canonical_url,
    collapse_whitespace,
    normalize_name,
    stable_id,
    strip_html,
    truncate,
)
from ..schemas import ProductRecord, validate_record
from .base import BaseCollector, CollectorContext, CollectorOutput

_SHOW_PREFIX = re.compile(r"^\s*show\s+hn\s*[:\-–]\s*", re.IGNORECASE)


class ShowHNCollector(BaseCollector):
    name = "showhn"
    record_type = "PRODUCT"

    def __init__(self, source_cfg: dict) -> None:
        super().__init__()
        self.cfg = source_cfg
        self.source_url = str(source_cfg.get("url", "https://hn.algolia.com/api/v1/search_by_date"))
        self.queries = list(source_cfg.get("queries") or ["AI", "LLM", "machine learning", "AI agent"])
        self.hits_per_page = int(source_cfg.get("hits_per_page", 500))
        self.max_pages_per_query = int(source_cfg.get("max_pages_per_query", 2))
        self.source_meta = {
            "source_name": source_cfg.get("name", 'Hacker News "Show HN"'),
            "source_url": self.source_url,
            "access_method": "public JSON API (Algolia HN Search)",
            "authentication": "none",
            "terms_url": source_cfg.get("terms_url"),
            "rate_limit": source_cfg.get("rate_limit"),
            "parser": "algolia_show_hn",
            "date_semantics": source_cfg.get("date_semantics"),
        }

    async def collect(self, ctx: CollectorContext) -> CollectorOutput:
        output = CollectorOutput(self.name, self.record_type, source_meta=self.source_meta)
        seen_hn_ids: set[str] = set()
        seen_urls: set[str] = set()
        seen_names: set[str] = set()

        for query in self.queries:
            for page in range(self.max_pages_per_query):
                params = {
                    "query": query,
                    "tags": "show_hn",
                    "hitsPerPage": self.hits_per_page,
                    "page": page,
                }
                try:
                    payload = await ctx.client.get_json(self.source_url, params=params, raw_label=f"query-{page}")
                except Exception as exc:  # noqa: BLE001 - one query failing should not kill the collector
                    output.notes.append(f"Query {query!r} page {page} failed: {exc}")
                    continue
                hits = payload.get("hits") or []
                if not hits:
                    break
                output.discovered += len(hits)
                for hit in hits:
                    self._parse_hit(hit, ctx, output, seen_hn_ids, seen_urls, seen_names)
                if len(hits) < self.hits_per_page:
                    break

        output.notes.append(
            f"{len(self.queries)} Algolia queries; discovered={output.discovered}; unique accepted={output.accepted}."
        )
        return output

    def _parse_hit(
        self,
        hit: dict,
        ctx: CollectorContext,
        output: CollectorOutput,
        seen_hn_ids: set[str],
        seen_urls: set[str],
        seen_names: set[str],
    ) -> None:
        hn_id = str(hit.get("objectID") or "")
        title_raw = collapse_whitespace(hit.get("title"))
        product_url = canonical_url(hit.get("url"))
        story_text = strip_html(hit.get("story_text"))

        if not hn_id or not title_raw:
            output.add_rejection("missing_identity", title_raw, f"https://news.ycombinator.com/item?id={hn_id}")
            return
        if hn_id in seen_hn_ids:
            output.add_rejection("duplicate_in_source", title_raw, f"https://news.ycombinator.com/item?id={hn_id}")
            return
        if not product_url:
            output.add_rejection("missing_product_url", title_raw, f"https://news.ycombinator.com/item?id={hn_id}")
            return

        title = _SHOW_PREFIX.sub("", title_raw).strip()
        title = re.sub(r"\s*\(.{0,60}\)\s*$", "", title).strip() or title_raw
        # Relevance is judged from the launch title only. Story text is kept as
        # description, but is not used to pull unrelated projects into the set.
        if not is_ai_related(title):
            output.add_rejection("not_ai_related", title, product_url)
            return
        if product_url in seen_urls or normalize_name(title) in seen_names:
            output.add_rejection("duplicate_in_source", title, product_url)
            return

        hn_url = f"https://news.ycombinator.com/item?id={hn_id}"
        try:
            record = ProductRecord(
                record_id=stable_id("PRODUCT", "showhn", hn_id),
                source={"name": self.source_meta["source_name"], "url": self.source_url},
                content={
                    "entityName": truncate(title, 300) or title,
                    "startupName": None,
                    "pricingModel": "UNKNOWN",
                    "productUrl": product_url,
                    "description": truncate(story_text, 2000),
                    "category": "Show HN launch",
                },
                provenance={"recordUrl": hn_url},
                collectedAt=iso_now(ctx.now),
            ).model_dump(mode="json")
            validate_record(record)
        except Exception as exc:  # noqa: BLE001
            output.add_rejection("schema_validation_failed", f"{title}: {exc}", hn_url)
            return

        output.records.append(record)
        seen_hn_ids.add(hn_id)
        seen_urls.add(product_url)
        seen_names.add(normalize_name(title))
