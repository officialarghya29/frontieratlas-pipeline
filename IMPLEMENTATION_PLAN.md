# Implementation Plan — FrontierAtlas

**Objective:** deliver the GraphOne / FrontierAtlas AI Engineer assessment as a real, reproducible data-engineering system: 1,000+ genuine startups, products and research papers; five AI news feeds; five AI/tech job boards; strict 24-hour freshness; LLM extraction with fallback; entity resolution; database persistence; six exports; six-tab Google Sheet; tests; README; three-page architecture PDF.

**Source of truth:** the master execution prompt supplied by the owner. No assessment PDF was present in the workspace, so the prompt's requirements were treated as the specification and every deliverable was verified against it.

## Phase 1 — Audit (completed)

- Inspected an empty workspace; no pre-existing code to preserve.
- Probed every proposed source live before implementation:
  - YC-OSS AI JSON: 1,906 companies, fields confirmed.
  - arXiv API: 5 categories, Atom fields and rate guidance confirmed.
  - Product Hunt Atom feed: 50 entries, launch date semantics confirmed.
  - Hacker News Algolia API: pagination and UTC `created_at` confirmed.
  - Hugging Face Spaces API: public metadata and descriptions confirmed.
  - Five RSS feeds: all live, timezone-aware `published` confirmed.
  - Himalayas, Remotive, Remote OK, Arbeitnow, Jobicy: all live JSON APIs, date fields inspected.
  - Papers with Code: archived/unavailable → disabled and documented.
  - AI Dev Jobs: 0 listings → excluded and documented.
- Recorded access method, authentication, terms URL, rate limit, parser and date semantics in `config/sources.yaml`.

## Phase 2 — Data collection (completed)

- Async HTTP client: per-domain semaphores, minimum intervals, bounded retries, Retry-After, 413/403 semantics, raw response retention.
- Collectors: YC, arXiv, Product Hunt, Show HN, HF Spaces, five RSS feeds, five job boards.
- Strict publication-date validation for jobs and news; future/stale/missing/naive timestamps rejected with reasons.
- Cross-source dedupe before persistence; idempotent upserts keyed by stable `record_id`.
- Actual result: 1,894 startups, 2,490 products, 1,314 papers, 214 jobs, 16 news, zero source failures.

## Phase 3 — Intelligence (completed, execution pending credentials)

- Provider-independent LLM orchestration: Gemini → Groq → DeepSeek; environment-only keys.
- Semantic chunking, 413 recursive splitting, deterministic merge, 429 Retry-After/backoff, circuit breaking, provider fallback.
- Conservative system prompt; evidence-backed extraction; null when unsupported.
- Without keys, extraction is marked pending and records remain valid; no invented fields.
- Entity resolution: exact, alias, non-shared domain, strictly guarded fuzzy; every decision logged.
- Actual result: 6 auto-matched (all non-shared domain evidence), 71 review-required, 2,413 no-match; 2,490 mapping rows.

## Phase 4 — Storage and exports (completed)

- SQLite WAL schema: records, revisions, mappings, aliases, source runs, checkpoints, collection runs.
- Idempotent upserts, revision audit, unique constraints, transactional batch writes.
- GitHub enrichment: 164/170 explicit repositories verified; nulls preserved on failure.
- CSV + JSONL for five datasets and the mapping log, plus manifest with SHA-256.
- Quality report with per-source counts, rejection reasons, missing fields, freshness, enrichment and tests.

## Phase 5 — Google Sheets (implemented, blocked)

- Six exact tab names, headers, frozen rows, filters, idempotent rewrite, secret scan before public sharing.
- No service-account key was supplied, so no spreadsheet was created and no public URL is claimed.
- Remaining step: set `GOOGLE_APPLICATION_CREDENTIALS` and run `python scripts/export_sheets.py`.

## Phase 6 — Verification (completed)

- 53 automated tests, mocked HTTP only, all passing.
- 0 schema validation issues across 5,928 records; all three count targets exceeded.
- Architecture PDF generated (must remain ≤3 pages; verified with pypdf).
- Repository scanned for credentials; `.env`, raw data and database artifacts ignored.
- Final submission form not submitted automatically (requires owner account).

## Key engineering decisions

- **SQLite for this submission, PostgreSQL path documented.** Zero-ops reproducibility with a schema that maps to Postgres.
- **Dedupe before write.** Prevents duplicates from ever entering the database, not merely from export.
- **Conservative entity resolution.** False merges are worse than missed associations; ambiguous cases are review-flagged.
- **No timezone assumptions.** Remotive timestamps rejected rather than assumed UTC.
- **No paid/restricted sources.** Public APIs/feeds only; blocks are recorded, never bypassed.
