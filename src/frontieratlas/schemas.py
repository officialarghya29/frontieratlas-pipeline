"""Canonical record schemas (Pydantic v2) for every dataset.

Every exported record contains schemaVersion, recordType, record_id, source,
content, provenance and collectedAt. Missing facts stay null; nothing is
inferred to fill a field.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .common.timeutil import TimestampError, iso_utc, parse_timestamp
from .common.text import canonical_url

SCHEMA_VERSION = "1.0"
PricingModel = Literal["FREE", "FREEMIUM", "PAID", "ENTERPRISE", "UNKNOWN"]
ExtractionStatus = Literal["FULL_TEXT", "SUMMARY_ONLY", "PENDING"]
RoleFamily = Literal[
    "Engineering",
    "Data",
    "Research",
    "Product",
    "Design",
    "Operations",
    "Sales",
    "Marketing",
    "Other",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _iso_or_raise(value: str) -> str:
    try:
        return iso_utc(parse_timestamp(value))
    except TimestampError as exc:
        raise ValueError(f"collectedAt must be a timezone-aware timestamp: {exc}") from exc


class SourceRef(StrictModel):
    name: str
    url: str


# --------------------------------------------------------------------------- #
# STARTUP
# --------------------------------------------------------------------------- #
class StartupData(StrictModel):
    employeeCount: int | None = None


class StartupContent(StrictModel):
    entityName: str
    data: StartupData = Field(default_factory=StartupData)
    website: str | None = None
    description: str | None = None
    foundedYear: int | None = None
    industry: str | None = None
    headquarters: str | None = None


class StartupProvenance(StrictModel):
    recordUrl: str


class StartupRecord(StrictModel):
    schemaVersion: Literal["1.0"] = SCHEMA_VERSION
    recordType: Literal["STARTUP"] = "STARTUP"
    record_id: str
    source: SourceRef
    content: StartupContent
    provenance: StartupProvenance
    collectedAt: str

    _check_collected = field_validator("collectedAt")(_iso_or_raise)


# --------------------------------------------------------------------------- #
# PRODUCT
# --------------------------------------------------------------------------- #
class ProductContent(StrictModel):
    entityName: str
    startupName: str | None = None
    pricingModel: PricingModel = "UNKNOWN"
    productUrl: str | None = None
    description: str | None = None
    category: str | None = None


class ProductProvenance(StrictModel):
    recordUrl: str


class ProductRecord(StrictModel):
    schemaVersion: Literal["1.0"] = SCHEMA_VERSION
    recordType: Literal["PRODUCT"] = "PRODUCT"
    record_id: str
    source: SourceRef
    content: ProductContent
    provenance: ProductProvenance
    collectedAt: str

    _check_collected = field_validator("collectedAt")(_iso_or_raise)


# --------------------------------------------------------------------------- #
# RESEARCH PAPER
# --------------------------------------------------------------------------- #
class ResearchPaperContent(StrictModel):
    title: str
    authors: list[str] = Field(default_factory=list)
    paper_url: str
    github_url: str | None = None
    github_stars: int | None = None
    github_checked_at: str | None = None
    published_date: str | None = None
    abstract: str | None = None


class PaperProvenance(StrictModel):
    recordUrl: str
    githubEvidenceUrl: str | None = None


class ResearchPaperRecord(StrictModel):
    schemaVersion: Literal["1.0"] = SCHEMA_VERSION
    recordType: Literal["RESEARCH_PAPER"] = "RESEARCH_PAPER"
    record_id: str
    source: SourceRef
    content: ResearchPaperContent
    provenance: PaperProvenance
    collectedAt: str

    _check_collected = field_validator("collectedAt")(_iso_or_raise)


# --------------------------------------------------------------------------- #
# JOB
# --------------------------------------------------------------------------- #
class JobContent(StrictModel):
    company: str
    date: str
    is_remote: bool | None = None
    role_family: RoleFamily = "Other"
    title: str
    job_url: str


class JobProvenance(StrictModel):
    recordUrl: str
    dateEvidence: str


class JobRecord(StrictModel):
    schemaVersion: Literal["1.0"] = SCHEMA_VERSION
    recordType: Literal["JOB"] = "JOB"
    record_id: str
    source: SourceRef
    content: JobContent
    provenance: JobProvenance
    freshness_verified: bool
    collectedAt: str

    _check_collected = field_validator("collectedAt")(_iso_or_raise)


# --------------------------------------------------------------------------- #
# NEWS
# --------------------------------------------------------------------------- #
class NewsContent(StrictModel):
    title: str
    date: str
    publisher: str
    full_text: str | None = None
    summary: str | None = None
    article_url: str


class NewsProvenance(StrictModel):
    recordUrl: str
    dateEvidence: str


class NewsRecord(StrictModel):
    schemaVersion: Literal["1.0"] = SCHEMA_VERSION
    recordType: Literal["NEWS"] = "NEWS"
    record_id: str
    source: SourceRef
    content: NewsContent
    provenance: NewsProvenance
    freshness_verified: bool
    extraction_status: ExtractionStatus = "SUMMARY_ONLY"
    collectedAt: str

    _check_collected = field_validator("collectedAt")(_iso_or_raise)


# --------------------------------------------------------------------------- #
# ENTITY MAPPING LOG
# --------------------------------------------------------------------------- #
class EntityMapping(StrictModel):
    raw_name: str
    canonical_name: str | None
    entity_type: Literal["STARTUP", "PRODUCT", "RESEARCH_PAPER", "JOB", "NEWS"]
    source_url: str
    method: str
    similarity_score: float = Field(ge=0, le=100)
    decision: Literal["AUTO_MATCHED", "REVIEW_REQUIRED", "NO_MATCH"]
    review_required: bool
    mapped_at: str
    notes: str | None = None


RECORD_MODELS: dict[str, type[StrictModel]] = {
    "STARTUP": StartupRecord,
    "PRODUCT": ProductRecord,
    "RESEARCH_PAPER": ResearchPaperRecord,
    "JOB": JobRecord,
    "NEWS": NewsRecord,
}


def validate_record(data: dict) -> StrictModel:
    record_type = data.get("recordType")
    model = RECORD_MODELS.get(str(record_type))
    if model is None:
        raise ValueError(f"unknown recordType: {record_type!r}")
    return model.model_validate(data)


def normalize_url_field(value: str | None) -> str | None:
    return canonical_url(value)
