#!/usr/bin/env python3
"""Build architecture.pdf (maximum three pages) with a vector architecture diagram."""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "architecture.pdf"


def diagram() -> Drawing:
    width, height = 500, 120
    drawing = Drawing(width, height)
    boxes = [
        ("Sources", ["YC-OSS AI (1,906)", "arXiv API", "RSS feeds", "job-board APIs"]),
        ("Async collectors", ["aiohttp + semaphores", "pacing, retries", "checkpoints", "raw retention"]),
        ("Canonical records", ["Pydantic schemas", "ISO-8601 UTC", "null-safe fields", "stable record_id"]),
        ("Persistence", ["SQLite now", "Postgres at scale", "idempotent upserts", "revision audit"]),
        ("Intelligence", ["GitHub stars", "entity resolution", "LLM fallback"]),
        ("Delivery", ["CSV / JSONL", "quality report", "six-tab Sheets"]),
    ]
    box_width, box_height, gap = 76, 70, 7.4
    y = 34
    for index, (title, lines) in enumerate(boxes):
        x = index * (box_width + gap)
        drawing.add(Rect(x, y, box_width, box_height, rx=4, ry=4, fillColor=colors.HexColor("#eef3fb"), strokeColor=colors.HexColor("#456a9e")))
        drawing.add(String(x + 5, y + box_height - 12, title, fontName="Helvetica-Bold", fontSize=7.6, fillColor=colors.HexColor("#17365d")))
        for row, line in enumerate(lines):
            drawing.add(String(x + 5, y + box_height - 25 - row * 9, line, fontName="Helvetica", fontSize=5.9, fillColor=colors.black))
        if index < len(boxes) - 1:
            start = x + box_width + 1
            drawing.add(Line(start, y + box_height / 2, start + gap - 2, y + box_height / 2, strokeColor=colors.HexColor("#456a9e")))
            drawing.add(Polygon([start + gap - 2, y + box_height / 2, start + gap - 5, y + box_height / 2 + 2.5, start + gap - 5, y + box_height / 2 - 2.5], fillColor=colors.HexColor("#456a9e"), strokeColor=colors.HexColor("#456a9e")))
    drawing.add(String(0, 12, "Every stage fails independently: a blocked or failing source is logged and skipped; raw responses remain replayable.", fontName="Helvetica-Oblique", fontSize=6.5, fillColor=colors.HexColor("#444444")))
    return drawing


def build() -> None:
    styles = getSampleStyleSheet()
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.6, leading=11.4, alignment=TA_LEFT, spaceAfter=3)
    small = ParagraphStyle("Small", parent=body, fontSize=7.6, leading=9.6, textColor=colors.HexColor("#333333"))
    h1 = ParagraphStyle("H1", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=17, leading=20, spaceAfter=2)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=10.5, leading=13, spaceBefore=7, spaceAfter=3, textColor=colors.HexColor("#17365d"))
    subtitle = ParagraphStyle("Subtitle", parent=body, fontSize=9, textColor=colors.HexColor("#555555"), spaceAfter=10)

    table_cell = ParagraphStyle(
        "TableCell",
        parent=body,
        fontSize=7.3,
        leading=8.9,
        spaceBefore=0,
        spaceAfter=0,
        splitLongWords=1,
    )
    table_header = ParagraphStyle(
        "TableHeader",
        parent=table_cell,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#17365d"),
    )

    def table(rows, widths, header=True):
        wrapped = []
        for row_index, row in enumerate(rows):
            cell_style = table_header if header and row_index == 0 else table_cell
            wrapped.append([Paragraph(escape(str(cell)), cell_style) for cell in row])
        style = [
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b8c6da")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ]
        if header:
            style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6eef9")))
        t = Table(wrapped, colWidths=widths, repeatRows=1 if header else 0)
        t.setStyle(TableStyle(style))
        return t

    story = [
        Paragraph("FrontierAtlas — Architecture", h1),
        Paragraph("AI ecosystem ingestion, entity resolution and delivery · 21 November 2026 · graphone / FrontierAtlas assessment", subtitle),
        Paragraph(
            "FrontierAtlas is a Python 3.12 asynchronous pipeline. Each source is fetched through one bounded HTTP layer "
            "(per-domain semaphores, minimum inter-request intervals, retry budgets, Retry-After handling, raw response retention). "
            "Collectors emit only canonical, schema-validated records with a stable id, source URL and UTC collection timestamp. "
            "Cross-source duplicates are removed before persistence, then surviving records are written with idempotent upserts. "
            "Enrichment and entity resolution are separate, auditable stages; exports are generated from the database, never from memory.",
            body,
        ),
        Spacer(1, 4),
        diagram(),
        Spacer(1, 6),
        Paragraph("Implemented versus proposed", h2),
        table(
            [
                ["Capability", "Status in this repository"],
                ["Async collection, pacing, retries, checkpoints, raw retention", "Implemented; 15 collectors enabled, 13 produced records"],
                ["Canonical schemas, validation, idempotent storage, audit revisions", "Implemented (SQLite; 5,928 records stored)"],
                ["Entity resolution + entity mapping log", "Implemented; 2,490 audited decisions"],
                ["GitHub star enrichment with explicit evidence only", "Implemented; 164 repositories verified"],
                ["LLM orchestration (Gemini → Groq → DeepSeek), 413/429, fallback", "Implemented and unit-tested; no provider keys supplied, so extraction is pending"],
                ["Google Sheets six-tab export, frozen headers, filters, public sharing", "Implemented; API blocked without credentials, six-tab XLSX staged for upload"],
                ["PostgreSQL, task queue, distributed workers for 500k+", "Proposed migration path; not claimed as implemented"],
            ],
            [7.2 * cm, 10.4 * cm],
        ),
        PageBreak(),
        Paragraph("Scaling to 500,000+ records without manual intervention", h2),
        Paragraph(
            "The current synchronous-async design is bounded by one process and SQLite, but its write path is shaped for horizontal scale. "
            "Collectors are source-partitioned: each source owns a cursor checkpoint in <i>checkpoints</i>, so workers can resume independently after "
            "a crash or deployment. A production deployment moves the same collector interface behind a durable queue (for example SQS or RabbitMQ): "
            "one task per (source, page) with visibility timeouts, source-level rate budgets, and dead-letter queues for exhausted retries. Workers remain "
            "stateless; the queue supplies backpressure and the checkpoint table makes duplicate delivery safe. Persistence moves to PostgreSQL with the same "
            "stable text primary keys, unique constraints and <i>INSERT … ON CONFLICT</i> upserts, batched in transactions of a few hundred rows. Raw payloads "
            "stay in object storage (S3) partitioned by source/date and addressed by content hash, enabling replay without re-crawling. "
            "Capacity growth is therefore linear in workers, with per-domain concurrency kept low by configuration rather than by adding machines blindly.",
            body,
        ),
        Paragraph(
            "Vector and graph stores are deliberately <b>not</b> on the ingestion hot path. At 500k records, the relational store remains the system of record; "
            "a graph projection (startups—products—papers—repositories) can be rebuilt asynchronously for relationship queries, and embeddings can be added for "
            "semantic candidate retrieval during entity resolution. Both are derived indexes: losing them costs a rebuild, never source data.",
            body,
        ),
        Paragraph("413 payload-too-large and 429 rate-limit handling", h2),
        Paragraph(
            "<b>413.</b> Input size is estimated before submission. Text is split on paragraph boundaries with sentence fallback and a configured character overlap, "
            "then each semantic chunk is extracted independently. If a provider still returns 413, that chunk is split again at the nearest boundary (maximum depth 3) "
            "and both halves are re-extracted; results are merged deterministically (first non-null scalar wins, lists union, nested dictionaries merge, conflicts recorded). "
            "Content is never silently discarded; a chunk that cannot be reduced is marked pending with the provider error preserved.",
            body,
        ),
        Paragraph(
            "<b>429.</b> The HTTP layer honours Retry-After, applies exponential backoff with jitter, caps the wait, and records a per-domain penalty window. The LLM layer "
            "retries within a configured budget, then moves to the next provider in order (Gemini → Groq → DeepSeek). A provider that fails repeatedly is circuit-broken for "
            "the run. Every failure, wait and fallback is logged with provider and attempt number. If all providers fail, the raw document and a pending status are retained; "
            "no field is invented to fill the gap.",
            body,
        ),
        Paragraph("Preventing duplicate news and jobs across distributed crawler workers", h2),
        Paragraph(
            "Deduplication is layered. (1) Within a source, canonical URL normalization removes tracking parameters, fragment identifiers, <i>www</i> and trailing slashes; "
            "articles are keyed by canonical URL and normalized title. (2) Across sources, a deterministic key (canonical job/article URL, falling back to normalized company+title) "
            "is checked before any write, so a job syndicated on two boards is stored once. (3) At the database, <i>record_id</i> is a stable hash derived from source identity and "
            "URL, protected by a primary key; repeated runs update the same row instead of appending. (4) In a distributed deployment the same guarantee is enforced by PostgreSQL "
            "unique constraints and transactional upserts inside each worker, while a shared dedupe table keyed by canonical URL/content hash arbitrates races. Content changes are "
            "captured in a revision table, so an updated article is observable without creating a duplicate record. The observed run had zero cross-source duplicate survivors.",
            body,
        ),
        PageBreak(),
        Paragraph("Why SQLite now, PostgreSQL and derived graph/vector indexes later", h2),
        Paragraph(
            "SQLite is the right local-development store for this submission: zero operations, WAL mode, transactional writes, and a schema that maps one-to-one onto PostgreSQL. "
            "It preserves the properties the pipeline depends on — stable primary keys, unique constraints, idempotent upserts, indexed record types, checkpoint storage and audit history — "
            "while keeping the repository reproducible on a reviewer's machine. It is not presented as a production cluster database. PostgreSQL is the target system of record because "
            "it adds concurrent writers, partial indexes, JSONB payloads with GIN indexes, table partitioning by record type or collection month, and mature backup/observability tooling. "
            "At 500k+ records, batch upserts, connection pooling and read replicas cover ingestion and export load; a task queue and source partitioning handle crawl throughput. "
            "A graph database is appropriate only for relationship-heavy traversal (shared investors, product→startup→paper chains) and a vector index only for semantic entity retrieval; "
            "both are rebuildable projections, not authoritative storage. This separation keeps integrity rules in one place and avoids dual-write inconsistency.",
            body,
        ),
        Paragraph("Data integrity and freshness invariants", h2),
        Paragraph(
            "Every record carries schemaVersion, recordType, record_id, source, content, provenance and an ISO-8601 UTC collectedAt. Validation is strict: unknown fields are rejected, "
            "pricing is one of five allowed values, and provenance URLs are mandatory. Missing facts remain null; seed names are used only to assist matching and are never exported as records. "
            "Job and news publication times must be timezone-aware and inside the 24-hour window; future timestamps beyond a five-minute skew are rejected, and crawl time is never substituted. "
            "Records with missing or ambiguous publication dates are excluded and logged by reason. GitHub repositories are accepted only when the paper text explicitly contains the repository URL, "
            "and star counts come from the GitHub REST API at a recorded UTC check time. A product is never assumed to be a startup's product: associations require exact name, alias, "
            "non-shared domain equality, or a high-confidence fuzzy match, and 71 ambiguous candidates are explicitly flagged for manual review.",
            body,
        ),
        Paragraph("Measured result at the time of writing", h2),
        table(
            [
                ["Dataset", "Records", "Evidence"],
                ["Startups", "1,894", "Unique YC AI companies (1,906 discovered)"],
                ["Products", "2,490", "1,977 Show HN launches, 494 HF Spaces, 19 Product Hunt"],
                ["Research papers", "1,314", "Unique arXiv ids across cs.AI/LG/CL/CV/RO"],
                ["Jobs", "214", "Strict 24h verified: Himalayas 43, Arbeitnow 107, Jobicy 64"],
                ["News", "16", "All five RSS feeds; 24h verified"],
                ["Entity mapping log", "2,490", "6 auto-matched, 71 review, 2,413 no-match"],
                ["Tests", "53 passing", "pytest, mocked HTTP, no live network"],
            ],
            [4.2 * cm, 3.0 * cm, 10.4 * cm],
        ),
        Spacer(1, 4),
        Paragraph(
            "Limitations are stated rather than hidden: no LLM keys were supplied, so extraction remains pending; no Google service-account key was supplied, so the public Sheet is not published; "
            "Remotive and Remote OK returned no listings that satisfied the strict 24-hour, timezone-aware rule at run time; 500k-record throughput has not been tested and is described only as a migration path.",
            small,
        ),
    ]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d5dce7"))
        canvas.setLineWidth(0.4)
        canvas.line(1.55 * cm, 1.02 * cm, A4[0] - 1.55 * cm, 1.02 * cm)
        canvas.setFont("Helvetica", 6.8)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(1.55 * cm, 0.72 * cm, "FrontierAtlas — Architecture")
        canvas.drawRightString(A4[0] - 1.55 * cm, 0.72 * cm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=1.55 * cm,
        rightMargin=1.55 * cm,
        topMargin=1.35 * cm,
        bottomMargin=1.25 * cm,
        title="FrontierAtlas Architecture",
        author="Arghya Bose",
        subject="GraphOne / FrontierAtlas AI Engineer assessment",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    build()
