#!/usr/bin/env python3
"""Run conservative LLM extraction over product descriptions.

Without provider credentials the script records a pending status and leaves
records untouched. With credentials it only accepts schema-valid values that
the model marks as evidence-backed; everything else remains null/UNKNOWN.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from frontieratlas.common.config import get_settings  # noqa: E402
from frontieratlas.common.http import AsyncHttpClient  # noqa: E402
from frontieratlas.extractors.llm import LLMExtractor  # noqa: E402
from frontieratlas.schemas import ProductRecord, validate_record  # noqa: E402
from frontieratlas.storage.db import Database  # noqa: E402

SCHEMA_HINT = """Extract product facts from the source content below.
Return JSON exactly like:
{"valid_entity": true, "record": {"pricingModel": "FREE|FREEMIUM|PAID|ENTERPRISE|UNKNOWN", "category": null, "startupName": null}, "evidence": {"pricingModel": "quoted source text or null", "category": "quoted source text or null"}}
Only include a non-null value when the source text explicitly supports it. Otherwise use null (or UNKNOWN for pricingModel)."""

ALLOWED_PRICING = {"FREE", "FREEMIUM", "PAID", "ENTERPRISE", "UNKNOWN"}


async def main_async(limit: int, record_type: str) -> int:
    settings = get_settings()
    db = Database(settings.database_path).connect()
    products = db.fetch_records("PRODUCT")[:limit]
    report = {
        "status": "pending",
        "record_type": record_type,
        "attempted": 0,
        "successes": 0,
        "failures": 0,
        "updated": 0,
        "provider_health": [],
        "reason": "",
    }

    try:
        async with AsyncHttpClient(settings.http, raw_dir=settings.raw_dir, source_tag="llm") as client:
            extractor = LLMExtractor(settings, client)
            report["provider_health"] = extractor.health()
            if not extractor.available:
                report["reason"] = (
                    "No provider credentials: set GEMINI_API_KEY, GROQ_API_KEY or DEEPSEEK_API_KEY. "
                    "Records and raw content are preserved; no field was guessed."
                )
            else:
                report["status"] = "completed"
                for product in products:
                    description = product["content"].get("description")
                    if not description:
                        continue
                    report["attempted"] += 1
                    result = await extractor.extract(description, SCHEMA_HINT)
                    if not result.valid_entity or not result.record:
                        report["failures"] += 1
                        continue
                    record = result.record
                    pricing = record.get("pricingModel")
                    if isinstance(pricing, str) and pricing.upper() in ALLOWED_PRICING:
                        product["content"]["pricingModel"] = pricing.upper()
                    category = record.get("category")
                    if isinstance(category, str) and category.strip():
                        product["content"]["category"] = category.strip()[:200]
                    try:
                        validated = validate_record(product)
                    except Exception:  # noqa: BLE001 - do not persist invalid output
                        report["failures"] += 1
                        continue
                    db.upsert_records([validated.model_dump(mode="json")])
                    report["successes"] += 1
                    report["updated"] += 1
                report["provider_health"] = extractor.health()
    finally:
        db.close()

    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    path = settings.processed_dir / "llm_extraction.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report | {"report_path": str(path)}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Conservative LLM extraction.")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--type", default="PRODUCT", choices=["PRODUCT"])
    args = parser.parse_args()
    return asyncio.run(main_async(args.limit, args.type))


if __name__ == "__main__":
    raise SystemExit(main())
