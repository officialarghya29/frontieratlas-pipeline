"""Hugging Face Spaces collector: deployed, publicly usable AI applications."""

from __future__ import annotations

from ..common.ids import iso_now
from ..common.text import canonical_url, collapse_whitespace, stable_id, truncate
from ..schemas import ProductRecord, validate_record
from .base import BaseCollector, CollectorContext, CollectorOutput


class HuggingFaceSpacesCollector(BaseCollector):
    name = "huggingface_spaces"
    record_type = "PRODUCT"

    def __init__(self, source_cfg: dict) -> None:
        super().__init__()
        self.cfg = source_cfg
        self.source_url = str(source_cfg.get("url", "https://huggingface.co/api/spaces"))
        self.page_size = int(source_cfg.get("page_size", 100))
        self.max_pages = int(source_cfg.get("max_pages", 8))
        self.source_meta = {
            "source_name": source_cfg.get("name", "Hugging Face Spaces"),
            "source_url": self.source_url,
            "access_method": "public JSON API",
            "authentication": "none",
            "terms_url": source_cfg.get("terms_url"),
            "rate_limit": source_cfg.get("rate_limit"),
            "parser": "hf_spaces_json",
            "date_semantics": source_cfg.get("date_semantics"),
        }

    async def collect(self, ctx: CollectorContext) -> CollectorOutput:
        output = CollectorOutput(self.name, self.record_type, source_meta=self.source_meta)
        seen: set[str] = set()

        for page in range(self.max_pages):
            params = {
                "limit": self.page_size,
                "skip": page * self.page_size,
                "full": "true",
            }
            try:
                spaces = await ctx.client.get_json(self.source_url, params=params, raw_label=f"page-{page}")
            except Exception as exc:  # noqa: BLE001
                output.notes.append(f"Page {page} failed: {exc}")
                break
            if not isinstance(spaces, list) or not spaces:
                break
            output.discovered += len(spaces)

            for space in spaces:
                self._parse_space(space, ctx, output, seen)

            if len(spaces) < self.page_size:
                break

        output.notes.append(
            f"HF Spaces pages requested={self.max_pages}; discovered={output.discovered}; accepted={output.accepted}."
        )
        return output

    def _parse_space(
        self,
        space: dict,
        ctx: CollectorContext,
        output: CollectorOutput,
        seen: set[str],
    ) -> None:
        space_id = collapse_whitespace(str(space.get("id") or ""))
        if not space_id:
            output.add_rejection("missing_identity", None, self.source_url)
            return
        if space_id in seen:
            output.add_rejection("duplicate_in_source", space_id, self.source_url)
            return
        if space.get("private"):
            output.add_rejection("private_resource", space_id, self.source_url)
            return

        card = space.get("cardData") or {}
        if not isinstance(card, dict):
            card = {}
        title = collapse_whitespace(str(card.get("title") or ""))
        short_description = collapse_whitespace(str(card.get("short_description") or ""))
        if not title:
            title = collapse_whitespace(space_id.rsplit("/", 1)[-1].replace("-", " ").replace("_", " ").title())
        if not title:
            output.add_rejection("missing_name", space_id, self.source_url)
            return
        if not short_description:
            output.add_rejection("missing_description", space_id, self.source_url)
            return

        product_url = canonical_url(f"https://huggingface.co/spaces/{space_id}")
        try:
            record = ProductRecord(
                record_id=stable_id("PRODUCT", "huggingface_spaces", space_id),
                source={"name": self.source_meta["source_name"], "url": self.source_url},
                content={
                    "entityName": truncate(title, 200) or title,
                    "startupName": None,
                    "pricingModel": "UNKNOWN",
                    "productUrl": product_url,
                    "description": truncate(short_description, 1500),
                    "category": None,
                },
                provenance={"recordUrl": product_url},
                collectedAt=iso_now(ctx.now),
            ).model_dump(mode="json")
            validate_record(record)
        except Exception as exc:  # noqa: BLE001
            output.add_rejection("schema_validation_failed", f"{space_id}: {exc}", self.source_url)
            return

        seen.add(space_id)
        output.records.append(record)
