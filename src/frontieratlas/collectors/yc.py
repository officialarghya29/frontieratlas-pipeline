"""Y Combinator AI company collector (YC-OSS public JSON mirror)."""

from __future__ import annotations

from datetime import datetime, timezone

from ..common.ids import iso_now
from ..common.text import canonical_url, collapse_whitespace, normalize_name, stable_id, truncate
from ..schemas import StartupRecord, validate_record
from .base import BaseCollector, CollectorContext, CollectorOutput


def _founded_year(epoch: object) -> int | None:
    if not isinstance(epoch, (int, float)) or isinstance(epoch, bool):
        return None
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).year
    except (OverflowError, OSError, ValueError):
        return None


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


class YCStartupCollector(BaseCollector):
    name = "yc_ai"
    record_type = "STARTUP"

    def __init__(self, source_cfg: dict) -> None:
        super().__init__()
        self.cfg = source_cfg
        self.source_url = str(source_cfg.get("url", "https://yc-oss.github.io/api/tags/ai.json"))
        self.source_meta = {
            "source_name": source_cfg.get("name", "Y Combinator (AI tag)"),
            "source_url": self.source_url,
            "access_method": source_cfg.get("access_method", "public JSON API"),
            "authentication": source_cfg.get("authentication", "none"),
            "terms_url": source_cfg.get("terms_url"),
            "rate_limit": source_cfg.get("rate_limit"),
            "parser": "yc_json",
            "date_semantics": source_cfg.get("date_semantics", "launched_at is a launch epoch, not a publication date"),
        }

    async def collect(self, ctx: CollectorContext) -> CollectorOutput:
        output = CollectorOutput(
            source_name=self.name,
            record_type=self.record_type,
            source_meta=self.source_meta,
        )
        response = await ctx.client.get(self.source_url, raw_label="companies")
        companies = response.json()
        if not isinstance(companies, list):
            raise ValueError("YC response is not a list of companies")

        output.discovered = len(companies)
        seen_slugs: set[str] = set()
        seen_names: set[str] = set()

        for company in companies:
            if not isinstance(company, dict):
                output.add_rejection("invalid_record", "company entry is not an object", self.source_url)
                continue

            name = collapse_whitespace(str(company.get("name") or ""))
            slug = collapse_whitespace(str(company.get("slug") or ""))
            if not name:
                output.add_rejection("missing_name", f"company id={company.get('id')}", self.source_url)
                continue
            name_key = normalize_name(name)
            if (slug and slug in seen_slugs) or name_key in seen_names:
                output.add_rejection("duplicate_in_source", name, self.source_url)
                continue

            website = canonical_url(company.get("website")) if company.get("website") else None
            description = truncate(
                collapse_whitespace(company.get("long_description")) or collapse_whitespace(company.get("one_liner")),
                4000,
            )
            if not website and not description:
                output.add_rejection("insufficient_evidence", name, self.source_url)
                continue

            industries = company.get("industries") or []
            industry = collapse_whitespace(str(company.get("industry") or ""))
            if not industry and isinstance(industries, list) and industries:
                industry = collapse_whitespace(", ".join(str(item) for item in industries[:3]))

            locations = collapse_whitespace(str(company.get("all_locations") or ""))
            headquarters = locations.split(";")[0].strip() if locations else None

            try:
                record = StartupRecord(
                    record_id=stable_id("STARTUP", "yc_ai", slug or name_key),
                    source={"name": self.source_meta["source_name"], "url": self.source_url},
                    content={
                        "entityName": name,
                        "data": {"employeeCount": _as_int(company.get("team_size"))},
                        "website": website,
                        "description": description,
                        "foundedYear": _founded_year(company.get("launched_at")),
                        "industry": industry or None,
                        "headquarters": headquarters or None,
                    },
                    provenance={
                        "recordUrl": f"https://www.ycombinator.com/companies/{slug or name_key.replace(' ', '-')}"
                    },
                    collectedAt=iso_now(ctx.now),
                ).model_dump(mode="json")
                validate_record(record)
            except Exception as exc:  # noqa: BLE001 - per-record isolation
                output.add_rejection("schema_validation_failed", f"{name}: {exc}", self.source_url)
                continue

            output.records.append(record)
            if slug:
                seen_slugs.add(slug)
            seen_names.add(name_key)

            former_names = company.get("former_names") or []
            if isinstance(former_names, list):
                for alias in former_names:
                    alias_text = collapse_whitespace(str(alias or ""))
                    if alias_text and normalize_name(alias_text) != name_key:
                        ctx.db.add_alias(name, alias_text, self.name)

        output.notes.append(f"{output.discovered} AI-tagged YC companies discovered; {output.accepted} accepted.")
        return output
