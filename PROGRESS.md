# Progress Log — FrontierAtlas

## 2026-11-21 — Final run

### Completed

- Audited all sources live before coding; documented unavailable sources instead of faking them.
- Implemented 15 async collectors (YC, arXiv, Product Hunt, Show HN, HF Spaces, 5 news feeds, 5 job boards); 13 produced accepted records.
- Implemented strict schemas, cross-source dedupe, idempotent SQLite storage with revision audit, checkpoints and source-run metadata.
- Implemented GitHub enrichment, auditable entity resolution, provider-independent LLM orchestration, CSV/JSONL exports, six-tab Google Sheets exporter, quality reporting and a measured benchmark.
- Wrote 53 automated tests (all passing, mocked network).
- Generated `architecture.pdf` (3 pages) and this documentation set.

### Files created

- `src/frontieratlas/` — collectors, common utilities, extractors, resolvers, enrichers, storage, exporters, quality, schemas.
- `scripts/` — `collect_all.py`, `enrich_github.py`, `resolve_entities.py`, `extract_llm.py`, `export_all.py`, `export_sheets.py`, `validate_all.py`, `verify_submission.py`, `benchmark.py`, `build_submission_workbook.py`, `build_architecture_pdf.py`, `build_readme_assets.py`, `build_sheet_imports.py`.
- `config/` — `settings.yaml`, `sources.yaml`, `seed_entities.txt`.
- `tests/unit/` — 9 test modules.
- `data/exports/` — six CSVs, six JSONL files, manifest, quality report, six-tab XLSX workbook.
- `data/google_sheets/` — one upload-ready XLSX, six numbered CSVs, manifest and start-here guide.
- `assets/readme/` — verified README charts, screenshots and asset index.
- `SUBMISSION.md`, `pyproject.toml`, `requirements-dev.txt` — publishing packet, package metadata and optional visual tooling.

### Tests executed

```text
pytest --junitxml=data/processed/junit.xml -q
53 passed, 0 failed, 0 errors, 0 skipped
```

### Actual dataset counts

| Type | Count |
| --- | ---: |
| STARTUP | 1,894 |
| PRODUCT | 2,490 |
| RESEARCH_PAPER | 1,314 |
| JOB | 214 |
| NEWS | 16 |
| ENTITY_MAPPING | 2,490 |

- Cross-source duplicates removed: 0 survivors (dedupe applied before persistence).
- Schema issues: 0.
- Raw responses retained: 46 files under `data/raw/final-20261121/`.

### Source outcomes

- YC AI: 1,906 discovered → 1,894 accepted (12 duplicate names).
- arXiv: 1,600 discovered → 1,314 unique accepted (286 cross-category duplicates).
- Show HN: 5,286 discovered → 1,977 accepted (relevance/identity filters).
- HF Spaces: 800 discovered → 494 accepted (306 missing descriptions).
- Product Hunt: 50 discovered → 19 accepted (AI relevance).
- News: all five feeds live; 16 records within 24h; full-text extraction where freely available, otherwise labelled `SUMMARY_ONLY`.
- Jobs: Himalayas 43, Arbeitnow 107, Jobicy 64; Remotive 0 (naive timestamps), Remote OK 0 (stale at run time).
- GitHub: 170 explicit repositories; 164 star counts verified; 4 missing; 2 renamed/no-match. Nulls preserved.
- Entity resolution: 6 auto (all domain), 71 review, 2,413 no-match; single-token aliases are review-only.
- LLM: pending — no provider credentials supplied; no field guessed.
- Google Sheets: blocked — no service-account credentials; CSV/JSONL complete; the `data/google_sheets/` handoff and six-tab XLSX are ready; no public URL claimed.

### Errors and resolutions

- Himalayas identity fields were `guid`/`applicationLink`, not `url` → collector corrected and pagination enabled via cursor.
- A YC startup listed an App Store URL as its website, causing all app-store products to "domain match" → shared hosting/store domains excluded; fuzzy auto-merge raised to 97 with length/character guards; stale associations cleared before re-resolution.
- All 51 initial tests passed after fixing three test-harness issues (missing monkeypatch parameters, URL query ordering, and a 413 split threshold that was too high for the test payload).
- Two GitHub lookups returned a different repository name (rename/redirect) → treated as failed lookups, stars left null.

### Remaining work

1. Provide Google service-account credentials and run `python scripts/export_sheets.py`; verify all six tabs, row counts and public viewer access.
2. Optionally provide LLM keys and rerun `python scripts/extract_llm.py`; pricing/category remain `UNKNOWN`/null until then.
3. Submit the form at `https://forms.gle/3JJhukomumTFueRW7` with the repository and Sheet URLs.
