# FrontierAtlas Data Quality Report

Generated: 2026-11-21T07:43:17Z
Collection run: final-20261121 (completed)

## Dataset counts

| Record type | Records |
| --- | ---: |
| JOB | 214 |
| NEWS | 16 |
| PRODUCT | 2,490 |
| RESEARCH_PAPER | 1,314 |
| STARTUP | 1,894 |
| Entity mappings | 2,490 |

## Targets

| Target | Required | Actual | Met |
| --- | ---: | ---: | :---: |
| STARTUP | 1,000 | 1,894 | yes |
| PRODUCT | 1,000 | 2,490 | yes |
| RESEARCH_PAPER | 1,000 | 1,314 | yes |

## Sources

| Source | Type | Discovered | Accepted | Rejected | Status |
| --- | --- | ---: | ---: | ---: | --- |
| yc_ai | STARTUP | 1,906 | 1,894 | 12 | ok |
| producthunt | PRODUCT | 50 | 19 | 31 | ok |
| showhn | PRODUCT | 5,286 | 1,977 | 3,309 | ok |
| huggingface_spaces | PRODUCT | 800 | 494 | 306 | ok |
| arxiv | RESEARCH_PAPER | 1,600 | 1,314 | 286 | ok |
| techcrunch_ai | NEWS | 20 | 5 | 15 | ok |
| theverge_ai | NEWS | 10 | 4 | 6 | ok |
| wired_ai | NEWS | 10 | 4 | 6 | ok |
| arstechnica | NEWS | 20 | 1 | 19 | ok |
| mit_tech_review | NEWS | 10 | 2 | 8 | ok |
| himalayas | JOB | 120 | 43 | 77 | ok |
| remotive | JOB | 16 | 0 | 16 | ok |
| remoteok | JOB | 99 | 0 | 99 | ok |
| arbeitnow | JOB | 300 | 107 | 193 | ok |
| jobicy | JOB | 100 | 64 | 36 | ok |

## Rejections by reason

| Reason | Count |
| --- | ---: |
| not_ai_related | 753 |
| duplicate_in_source | 334 |
| missing_description | 306 |
| stale_publication_timestamp | 172 |
| missing_product_url | 29 |
| invalid_publication_date | 16 |

## Missing field statistics

### STARTUP

| Field | Present | Missing | Missing % |
| --- | ---: | ---: | ---: |
| content.entityName | 1,894 | 0 | 0.0% |
| content.data.employeeCount | 1,856 | 38 | 2.01% |
| content.website | 1,870 | 24 | 1.27% |
| content.description | 1,892 | 2 | 0.11% |
| content.foundedYear | 1,894 | 0 | 0.0% |
| content.industry | 1,894 | 0 | 0.0% |
| content.headquarters | 1,868 | 26 | 1.37% |
| provenance.recordUrl | 1,894 | 0 | 0.0% |

### PRODUCT

| Field | Present | Missing | Missing % |
| --- | ---: | ---: | ---: |
| content.entityName | 2,490 | 0 | 0.0% |
| content.startupName | 10 | 2,480 | 99.6% |
| content.pricingModel | 2,490 | 0 | 0.0% |
| content.productUrl | 2,490 | 0 | 0.0% |
| content.description | 1,244 | 1,246 | 50.04% |
| content.category | 1,996 | 494 | 19.84% |
| provenance.recordUrl | 2,490 | 0 | 0.0% |

### RESEARCH_PAPER

| Field | Present | Missing | Missing % |
| --- | ---: | ---: | ---: |
| content.title | 1,314 | 0 | 0.0% |
| content.authors | 1,314 | 0 | 0.0% |
| content.paper_url | 1,314 | 0 | 0.0% |
| content.github_url | 170 | 1,144 | 87.06% |
| content.github_stars | 164 | 1,150 | 87.52% |
| content.github_checked_at | 164 | 1,150 | 87.52% |
| content.published_date | 1,314 | 0 | 0.0% |
| content.abstract | 1,314 | 0 | 0.0% |

### JOB

| Field | Present | Missing | Missing % |
| --- | ---: | ---: | ---: |
| content.company | 214 | 0 | 0.0% |
| content.date | 214 | 0 | 0.0% |
| content.is_remote | 214 | 0 | 0.0% |
| content.role_family | 214 | 0 | 0.0% |
| content.title | 214 | 0 | 0.0% |
| content.job_url | 214 | 0 | 0.0% |
| provenance.dateEvidence | 214 | 0 | 0.0% |

### NEWS

| Field | Present | Missing | Missing % |
| --- | ---: | ---: | ---: |
| content.title | 16 | 0 | 0.0% |
| content.date | 16 | 0 | 0.0% |
| content.publisher | 16 | 0 | 0.0% |
| content.full_text | 11 | 5 | 31.25% |
| content.summary | 16 | 0 | 0.0% |
| content.article_url | 16 | 0 | 0.0% |
| provenance.dateEvidence | 16 | 0 | 0.0% |

## Freshness verification

Policy: published within 24h, clock skew 5m.

- News: 16/16 verified; date range 2026-11-20T11:00:00Z → 2026-11-20T23:24:02Z; 11 full text, 5 summary only.
- Jobs: 214/214 verified; date range 2026-11-20T09:40:13Z → 2026-11-21T07:03:43Z; 114 remote.
- Freshness rejections: {"stale_publication_timestamp": 172, "invalid_publication_date": 16}

## GitHub enrichment

- Papers: 1,314
- Papers with explicit repository evidence: 170
- Papers with verified star counts: 164
- Median stars: 0.0
- Maximum stars: 38630

## Entity resolution

- Decisions: {"NO_MATCH": 2413, "REVIEW_REQUIRED": 67, "AUTO_MATCHED": 10}
- Methods: {"not_name_like": 1918, "fuzzy_token_set": 562, "alias_match": 4, "domain_match": 6}
- Manual review required: 67

## LLM extraction

- Status: pending
- Reason: No provider credentials: set GEMINI_API_KEY, GROQ_API_KEY or DEEPSEEK_API_KEY. Records and raw content are preserved; no field was guessed.

## API failures

- None

## Tests

- 53 passed, 0 failed, 0 errors
