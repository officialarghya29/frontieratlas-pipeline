# FrontierAtlas — AI Ecosystem Ingestion & Intelligence Pipeline

Submission for the **GraphOne / FrontierAtlas AI Engineer assessment**.

FrontierAtlas collects, normalizes, resolves, enriches and exports real AI-ecosystem data from public sources. It is built as a modular async Python pipeline with strict provenance, idempotent storage, auditable entity resolution, and a six-tab Google Sheets export path.

**Repository:** https://github.com/officialarghya29/frontieratlas-pipeline
**Architecture:** [architecture.pdf](architecture.pdf) (3 pages)
**Run date:** 2026-11-21 (UTC)

## Verified dataset counts

| Deliverable | Records | Source evidence |
| --- | ---: | --- |
| Startups | **1,894** | Unique YC AI companies (1,906 discovered; 12 duplicates removed) |
| Products | **2,490** | 1,977 Show HN launches, 494 Hugging Face Spaces, 19 Product Hunt launches |
| Research papers | **1,314** | Unique arXiv IDs across cs.AI, cs.LG, cs.CL, cs.CV, cs.RO |
| Jobs | **214** | Himalayas 43, Arbeitnow 107, Jobicy 64 (all publication-verified within 24h) |
| News | **16** | TechCrunch 5, The Verge 4, WIRED 4, Ars Technica 1, MIT Technology Review 2 (all within 24h) |
| Entity Mapping Log | **2,490** | 10 auto-matched, 67 review-required, 2,413 no-match |

All 5,928 canonical records pass schema validation. **Zero** fabricated records, repositories, star counts, dates or URLs are included.

> **Status of the Google Sheet:** the exporter is implemented and validated at the mapping level, but **the public Google Sheet has not been published** because no Google service-account credentials were supplied. CSV/JSONL exports are complete in [`data/exports/`](data/exports). See [Google Sheets](#google-sheets) for the single remaining command.

## Architecture

```text
Public sources                Async collection              Canonical records
YC-OSS AI JSON   ─┐           aiohttp + per-domain          Pydantic schemas
arXiv Atom API   ─┤           semaphores + pacing           ISO-8601 UTC
5 RSS feeds      ─┼─────────▶ retries + Retry-After  ─────▶ stable record_id
5 job-board APIs ─┤           checkpoints + raw retention   provenance URLs
Product feeds    ─┘                    │
                                      ▼
                           cross-source dedupe (before write)
                                      │
                                      ▼
                    SQLite (Postgres-compatible schema)
                    idempotent upserts + revision audit
                           │                      │
                           ▼                      ▼
                 GitHub star enrichment    entity resolution
                 (explicit evidence only)  (audited mapping log)
                           │                      │
                           └──────────┬───────────┘
                                      ▼
                    CSV / JSONL / six-tab Google Sheet
                    + data quality report
```

The full technical rationale, including 500k-record scaling, 413/429 handling, and distributed deduplication, is in [architecture.pdf](architecture.pdf). Fifteen collectors are enabled; 13 produced accepted records on this run (Remotive and Remote OK were monitored but had no 24h-verifiable listings).

## Technology stack

- Python 3.11+ (tested on 3.12)
- `asyncio` / `aiohttp` with bounded concurrency and connection pooling
- Pydantic v2 schemas
- SQLite (WAL) with PostgreSQL-compatible DDL and idempotent upserts
- `feedparser` / BeautifulSoup for RSS and permitted article text
- RapidFuzz for conservative entity candidate matching
- GitHub REST API for repository stars
- Google Sheets + Drive APIs (service account)
- pytest / pytest-asyncio (53 tests, all passing)

## Repository layout

```text
src/frontieratlas/
  collectors/      YC, arXiv, Product Hunt, Show HN, HF Spaces, 5 RSS feeds, 5 job boards
  parsers/         (feed parsing lives with its collector)
  normalizers/     text/URL/name normalization in common/
  extractors/      provider-independent LLM orchestration (Gemini→Groq→DeepSeek)
  resolvers/       exact, alias, domain and fuzzy entity resolution
  enrichers/       GitHub repository star enrichment
  storage/         SQLite persistence, upserts, revisions, checkpoints
  exporters/       CSV/JSONL and Google Sheets
  quality/         dedupe keys, secret scanning, data quality report
  common/          config, HTTP, timestamps, text, logging
config/
  settings.yaml    runtime, freshness, LLM and resolution thresholds
  sources.yaml     every source, access method, terms, limits, date semantics
  seed_entities.txt  matching assistance only (never exported)
scripts/
  collect_all.py   full async collection
  enrich_github.py GitHub stars for explicit paper repositories
  resolve_entities.py product→startup resolution + mapping log
  extract_llm.py   conservative LLM extraction (pending without keys)
  export_all.py    six CSV/JSONL datasets + manifest
  export_sheets.py six-tab Sheet creation, formatting, public sharing
  build_submission_workbook.py  six-tab XLSX for Google Sheets upload
  validate_all.py  schema revalidation + quality report
  verify_submission.py  full pre-submission preflight
  benchmark.py     measured local write throughput
  build_architecture_pdf.py
tests/unit/        53 tests, mocked HTTP only
data/exports/      committed deliverables, workbook and quality report
SUBMISSION.md      copy-paste submission packet and publishing steps
```

## Data sources

| Source | Type | Access | Auth | Records accepted | Notes |
| --- | --- | --- | --- | ---: | --- |
| YC-OSS AI tag | Startups | Public JSON | None | 1,894 | `https://yc-oss.github.io/api/tags/ai.json` |
| arXiv API | Papers | Public Atom | None | 1,314 | 3s request spacing; 5 categories |
| Product Hunt Atom feed | Products | Public feed | None | 19 | AI-relevant launches only |
| Hacker News Show HN (Algolia) | Products | Public JSON | None | 1,977 | AI keyword in launch title; external URL required |
| Hugging Face Spaces | Products | Public JSON | None | 494 | Public deployed apps with descriptions |
| TechCrunch AI | News | RSS | None | 5 | 24h window |
| The Verge AI | News | RSS | None | 4 | 24h window |
| WIRED AI | News | RSS | None | 4 | 24h window |
| Ars Technica | News | RSS | None | 1 | 24h window |
| MIT Technology Review | News | RSS | None | 2 | 24h window |
| Himalayas | Jobs | Public JSON | None | 43 | Cursor pagination; epoch `pubDate` |
| Arbeitnow | Jobs | Public JSON | None | 107 | Epoch `created_at`; remote flag |
| Jobicy | Jobs | Public JSON | None | 64 | Timezone-aware `pubDate` |
| Remotive | Jobs | Public JSON | None | 0 | Monitored; timestamps have no timezone, so none can be 24h-verified (documented) |
| Remote OK | Jobs | Public JSON | None | 0 | Monitored; all listings were older than 24h at run time |
| GitHub REST API | Enrichment | Public API | Optional token | 164 | 170 papers had explicit repo links |
| Papers with Code | Papers | — | — | 0 | Disabled: service archived by Meta; documented, not faked |
| AI Dev Jobs | Jobs | Public HTML | None | 0 | Probed live: empty board (0 listings), excluded |

Every source's access method, authentication, terms URL, rate limit, parser, date-field semantics and last validation are recorded in `config/sources.yaml`. Source failures are isolated and reported; no CAPTCHA, Cloudflare, login wall, paywall or anti-bot control is bypassed.

## Installation (Linux)

```bash
git clone https://github.com/officialarghya29/frontieratlas-pipeline.git
cd frontieratlas-pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Python 3.11 or newer is required.

## Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `GITHUB_TOKEN` | Optional | Raises GitHub REST limit from 60 to 5,000 req/h for star enrichment |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Optional | First LLM provider |
| `GROQ_API_KEY` / `GROQ_MODEL` | Optional | Fallback LLM provider |
| `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` | Optional | Final fallback provider |
| `GOOGLE_APPLICATION_CREDENTIALS` | For Sheets | Path to a service-account JSON key, kept outside this repository |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | Optional | Existing spreadsheet to repopulate; otherwise a new one is created |
| `GOOGLE_SHEETS_SHARE_WITH` | Optional | Email to grant writer access (public reader access is granted separately) |
| `FRONTIERATLAS_LOG_LEVEL` | Optional | `INFO` by default |

No credential is committed, logged, exported, or written to `config/`. `.env`, service-account keys and raw responses are git-ignored. `.env.example` contains placeholders only.

## Database setup

No external database is required for local reproduction: SQLite is created automatically at `data/frontieratlas.db` in WAL mode.

```bash
python - <<'PY'
from frontieratlas.storage.db import Database
Database("data/frontieratlas.db").connect().close()
PY
```

The schema (`records`, `record_revisions`, `entity_mappings`, `entity_aliases`, `source_runs`, `checkpoints`, `collection_runs`) uses PostgreSQL-compatible types and constraints. To migrate, create the same tables in PostgreSQL and point a repository layer at `psycopg`; no collector or schema change is required. At 500k+ records, use batch upserts, connection pooling, partitioning by record type/month, and a durable queue with source-partitioned workers (see `architecture.pdf`).

## Collection commands

```bash
# Full collection (15 enabled collectors, ~30s)
python scripts/collect_all.py

# One source or a subset
python scripts/collect_all.py --only yc_ai,arxiv
python scripts/collect_all.py --only techcrunch_ai,arstechnica

# GitHub star enrichment (only explicit paper→repo evidence)
export GITHUB_TOKEN="..."
python scripts/enrich_github.py --limit 400

# Entity resolution → Entity Mapping Log
python scripts/resolve_entities.py

# LLM extraction (writes a pending report if no provider keys exist)
python scripts/extract_llm.py --limit 25
```

Collection is idempotent: rerunning upserts by `record_id` and does not duplicate rows. Cross-source duplicates are removed before persistence. Raw payloads are retained under `data/raw/<run-id>/`.

## Validation, testing, exports

```bash
# Full test suite (53 tests, no live network)
pytest

# Revalidate every stored record against its schema + write quality report
python scripts/validate_all.py

# CSV + JSONL for all six deliverables, plus manifest with SHA-256
python scripts/export_all.py

# Credential-free six-tab workbook for Google Sheets upload
python scripts/build_submission_workbook.py

# Preflight every submission requirement (counts, schemas, PDF, tests, identity, secrets)
python scripts/verify_submission.py

# Measured local upsert throughput (synthetic rows, isolated DB, deleted after)
python scripts/benchmark.py

# Regenerate the 3-page architecture PDF
python scripts/build_architecture_pdf.py
```

Validation output at run time: **0 schema issues**, all three count targets met.

Data quality report: [`data/exports/data_quality_report.md`](data/exports/data_quality_report.md) and `.json`. It contains per-source discovered/accepted/rejected counts, rejection reasons, missing-field percentages, freshness verification, GitHub enrichment results, LLM success/failure status, API failures, duplicate counts and collection timestamps.

## Google Sheets

The exporter creates exactly six tabs:

1. `Startups`
2. `Products`
3. `Research Papers`
4. `Jobs`
5. `News`
6. `Entity Mapping Log`

It writes readable headers, freezes the header row, applies filters, batches writes, clears managed tabs before rewriting (idempotent, no duplicate rows), scans every cell for credential-shaped strings, and only grants public reader access after that scan passes.

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/secure/path/service-account.json"
python scripts/export_sheets.py
```

Required Google setup: create a service account, enable the **Google Sheets API** and **Google Drive API**, download the JSON key outside the repository, and grant that service account access if reusing an existing spreadsheet.

### Fastest path (no Google Cloud setup)

`data/exports/FrontierAtlas_submission.xlsx` is a styled, six-tab workbook ready for upload:

1. Upload it to Google Drive.
2. Right-click → **Open with** → **Google Sheets** (save as a Google Sheet if prompted).
3. **Share** → **General access** → **Anyone with the link** → **Viewer**.
4. Paste the Sheet URL into the submission form.

Verify the six tab names and these row counts: Startups 1,894; Products 2,490; Research Papers 1,314; Jobs 214; News 16; Entity Mapping Log 2,490.

### API path (automatic)

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/secure/path/service-account.json"
python scripts/export_sheets.py            # creates, populates, publishes, prints URL
python scripts/export_sheets.py --dry-run  # validate payloads without credentials
```

**Current status:** the API export is **blocked** because `GOOGLE_APPLICATION_CREDENTIALS` is not set on this machine, so no Sheet URL is claimed here. The staging workbook and all CSV/JSONL exports are complete and committed.

## Data integrity rules enforced

- No fabricated companies, products, papers, authors, dates, employee counts, pricing, repositories, stars, jobs, articles or URLs.
- Missing values remain `null`; pricing defaults to `UNKNOWN` (allowed set: `FREE`, `FREEMIUM`, `PAID`, `ENTERPRISE`, `UNKNOWN`).
- Every record has a real source URL and provenance record URL.
- Publication timestamps must be timezone-aware UTC; naive, missing, stale (>24h) and future (>5min skew) timestamps are rejected and logged by reason.
- Crawl time is never used as publication time.
- GitHub repositories are never guessed from paper titles; only explicit URLs in the abstract/comment/journal reference are used, and star lookups occur at a recorded UTC check time.
- Seed startup names assist matching only and are never exported as collected records.
- Product→startup associations require exact name, verified alias, non-shared domain equality, or a strict fuzzy match; ambiguous candidates are flagged for manual review, never auto-merged.

## Entity resolution

Matching order: exact normalized name → verified alias (YC former names) → non-shared website-domain equality → fuzzy token-set with length and character-ratio guards. Thresholds live in `config/settings.yaml`.

At run time: 2,490 products produced 10 auto-matches (6 domain, 4 alias), 67 review-required and 2,413 no-match. Every decision — including no-match — is recorded with raw name, canonical name, method, score, decision, review flag, timestamp and evidence notes.

## Known limitations

1. **Google Sheet not yet published** — no service-account credentials were supplied, so the API export could not run. A complete six-tab XLSX staging workbook is provided; uploading and sharing it is the only remaining submission step.
2. **LLM extraction not executed** — implemented with Gemini→Groq→DeepSeek fallback, 413 chunking and 429 backoff, and unit-tested with mocked providers, but no API keys were supplied. Records remain valid with deterministic fields; pricing is `UNKNOWN` where unverified.
3. **Remotive and Remote OK produced zero accepted jobs** — Remotive's `publication_date` has no timezone (cannot be 24h-verified), and Remote OK's listings were all older than 24h at run time. Both remain monitored and documented rather than relaxed.
4. **Product quality is source-shaped** — Show HN and HF Spaces are public launch/app sources, not a commercial product database. Product Hunt's public feed supplied only 19 AI-relevant launches. Pricing is therefore mostly `UNKNOWN`.
5. **Entity association is conservative** — most products are launch titles, not canonical company names; 67 ambiguous candidates await manual review.
6. **SQLite is local-development storage** — production PostgreSQL, task queues and distributed workers are an architectural migration path, not implemented at 500k scale.
7. **No 500k claim** — only the 5,928 rows collected here were processed; `scripts/benchmark.py` measures local write throughput separately and does not constitute a 500k test.
8. **GitHub enrichment partial** — 164/170 explicit repositories verified; 4 were missing/deleted and 2 did not match the requested repository name. Star counts remain `null` rather than guessed.
9. **Papers with Code disabled** — the service was archived; GitHub evidence is taken only from arXiv text.
10. **AI Dev Jobs excluded** — the public board returned zero listings when probed.

## Implemented vs proposed

**Implemented:** async source collection; bounded concurrency and pacing; retries/backoff/Retry-After; checkpoints; raw retention; cross-source dedupe; strict schemas; idempotent upserts; revision audit; GitHub enrichment; entity resolution and mapping log; LLM provider abstraction with 413/429/fallback; CSV/JSONL export; six-tab Sheets exporter with formatting/publication guard; credential-free six-tab XLSX workbook; pre-submission verifier; quality report; 53 automated tests; three-page architecture PDF.

**Proposed / not implemented:** PostgreSQL production deployment, durable queue, distributed workers, 500k-record throughput validation, graph database projection, vector search for entity retrieval, automated manual-review UI.

## Reproduction sequence

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                      # optional keys only
python scripts/collect_all.py             # 15 enabled collectors, real data
python scripts/enrich_github.py           # optional GITHUB_TOKEN
python scripts/resolve_entities.py
python scripts/extract_llm.py             # pending without LLM keys
python scripts/export_all.py
python scripts/validate_all.py
python scripts/build_submission_workbook.py
pytest
python scripts/build_architecture_pdf.py
python scripts/verify_submission.py
python scripts/export_sheets.py           # optional API path; needs service-account credentials
```

## Source attribution

Data remains attributable to its publishers: Y Combinator (via the YC-OSS mirror), arXiv, Product Hunt, Hacker News (Algolia Search API), Hugging Face, TechCrunch, The Verge, WIRED, Ars Technica, MIT Technology Review, Himalayas, Remotive, Remote OK, Arbeitnow, Jobicy and GitHub. Each record stores the original source and provenance URLs. Terms and access methods are documented per source in `config/sources.yaml`. No source content is redistributed beyond the assessment's data-collection purpose.

## Final submission form

The form at `https://forms.gle/3JJhukomumTFueRW7` has **not** been submitted automatically; it requires the owner's account and final confirmation. Copy-paste answers, Sheet publishing steps and remaining credential-gated actions are in [`SUBMISSION.md`](SUBMISSION.md).
