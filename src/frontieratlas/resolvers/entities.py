"""Auditable entity resolution.

Matching order (strongest first):
1. exact normalized name
2. exact alias (YC former names or seed aliases)
3. verified website-domain equality
4. fuzzy token-set similarity (auto-merge only at/above the configured threshold)

Every decision is recorded, including NO_MATCH, so the Entity Mapping Log is a
complete audit trail. Products are never assigned a startup on weak evidence;
ambiguous fuzzy matches are flagged for manual review.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process

from ..common.config import EntityResolutionSettings, PROJECT_ROOT
from ..common.ids import iso_now
from ..common.logging import get_logger
from ..common.text import domain_of, name_key, normalize_name
from ..schemas import EntityMapping
from ..storage.db import Database

# Hosts where domain equality says nothing about company ownership: app stores,
# code hosts, social platforms, and shared application hosting.
SHARED_HOSTS = {
    "apps.apple.com",
    "play.google.com",
    "github.com",
    "gitlab.com",
    "huggingface.co",
    "producthunt.com",
    "news.ycombinator.com",
    "youtube.com",
    "youtu.be",
    "x.com",
    "twitter.com",
    "linkedin.com",
    "medium.com",
    "substack.com",
    "notion.so",
    "notion.site",
    "figma.com",
    "docs.google.com",
    "reddit.com",
    "discord.com",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "vimeo.com",
    "spotify.com",
    "chromewebstore.google.com",
    "addons.mozilla.org",
    "npmjs.com",
    "pypi.org",
    "kaggle.com",
    "colab.research.google.com",
    "replit.com",
    "codepen.io",
    "observablehq.com",
    "github.io",
    "gitlab.io",
    "webflow.io",
    "wixsite.com",
    "squarespace.com",
    "wordpress.com",
    "blogspot.com",
    "gitbook.io",
    "readme.io",
    "onrender.com",
    "fly.dev",
    "railway.app",
    "render.com",
    "glitch.me",
    "surge.sh",
}

# A one-word alias (for example "BOOM" or "Trellis") collides with too many
# unrelated product titles. Multi-word aliases may auto-match; single-token
# aliases are deliberately review-only.
MIN_AUTO_ALIAS_TOKENS = 2
SHARED_SUFFIXES = (
    ".hf.space",
    ".gradio.live",
    ".streamlit.app",
    ".vercel.app",
    ".netlify.app",
    ".web.app",
    ".firebaseapp.com",
    ".pages.dev",
    ".workers.dev",
    ".herokuapp.com",
)


def is_shared_domain(domain: str | None) -> bool:
    if not domain:
        return True
    return domain in SHARED_HOSTS or any(domain.endswith(suffix) for suffix in SHARED_SUFFIXES)


@dataclass
class Candidate:
    canonical_name: str
    name_key: str
    domain: str | None
    source_url: str
    is_seed: bool = False


@dataclass
class ResolveStats:
    products_total: int = 0
    auto_matched: int = 0
    review_required: int = 0
    no_match: int = 0
    product_records_updated: int = 0
    methods: dict[str, int] | None = None

    def as_dict(self) -> dict:
        return {
            "products_total": self.products_total,
            "auto_matched": self.auto_matched,
            "review_required": self.review_required,
            "no_match": self.no_match,
            "product_records_updated": self.product_records_updated,
            "methods": self.methods or {},
        }


class EntityResolver:
    def __init__(self, settings: EntityResolutionSettings, db: Database) -> None:
        self.settings = settings
        self.db = db
        self.log = get_logger("resolver.entities")
        self.startups: list[Candidate] = []
        self.seeds: list[Candidate] = []
        self._startup_by_key: dict[str, Candidate] = {}
        self._startup_by_alias: dict[str, Candidate] = {}
        self._startup_by_domain: dict[str, Candidate | None] = {}
        self._seed_by_key: dict[str, Candidate] = {}
        self._load()

    def _load(self) -> None:
        for record in self.db.fetch_records("STARTUP"):
            content = record.get("content", {})
            name = str(content.get("entityName") or "").strip()
            if not name:
                continue
            key = name_key(name)
            if not key:
                continue
            candidate = Candidate(
                canonical_name=name,
                name_key=key,
                domain=domain_of(content.get("website")),
                source_url=str(record.get("provenance", {}).get("recordUrl") or ""),
            )
            self.startups.append(candidate)
            self._startup_by_key.setdefault(key, candidate)
            if candidate.domain:
                existing = self._startup_by_domain.get(candidate.domain)
                if existing is None and candidate.domain not in self._startup_by_domain:
                    self._startup_by_domain[candidate.domain] = candidate
                elif existing is not None and existing.canonical_name != candidate.canonical_name:
                    # Two startups share a domain: domain evidence is ambiguous.
                    self._startup_by_domain[candidate.domain] = None

        aliases = self.db.fetch_aliases()
        for canonical, alias_list in aliases.items():
            key = name_key(canonical)
            candidate = self._startup_by_key.get(key)
            if candidate is None:
                continue
            for alias in alias_list:
                alias_key = name_key(alias)
                if alias_key and alias_key != key:
                    self._startup_by_alias.setdefault(alias_key, candidate)

        seed_path = Path(self.settings.seed_entity_file)
        if not seed_path.is_absolute():
            seed_path = PROJECT_ROOT / seed_path
        if seed_path.exists():
            for line in seed_path.read_text(encoding="utf-8").splitlines():
                text = line.strip()
                if not text or text.startswith("#"):
                    continue
                key = name_key(text)
                if not key or key in self._startup_by_key:
                    continue
                seed = Candidate(
                    canonical_name=text,
                    name_key=key,
                    domain=None,
                    source_url=str(seed_path),
                    is_seed=True,
                )
                self.seeds.append(seed)
                self._seed_by_key.setdefault(key, seed)

        self._startup_keys = [candidate.name_key for candidate in self.startups]

    def resolve(self, raw_name: str, source_url: str) -> EntityMapping:
        key = name_key(raw_name)
        normalized = normalize_name(raw_name)
        now = iso_now()

        def mapping(
            canonical: str | None,
            method: str,
            score: float,
            decision: str,
            notes: str | None = None,
        ) -> EntityMapping:
            return EntityMapping(
                raw_name=raw_name[:300] or "(empty)",
                canonical_name=canonical,
                entity_type="PRODUCT",
                source_url=source_url or "",
                method=method,
                similarity_score=round(float(score), 2),
                decision=decision,  # type: ignore[arg-type]
                review_required=decision == "REVIEW_REQUIRED",
                mapped_at=now,
                notes=notes[:500] if notes else None,
            )

        if not key:
            return mapping(None, "no_name", 0, "NO_MATCH", "empty normalized name")

        exact = self._startup_by_key.get(key)
        if exact and not exact.is_seed:
            return mapping(exact.canonical_name, "exact_name", self.settings.exact_threshold, "AUTO_MATCHED")

        alias = self._startup_by_alias.get(key)
        if alias:
            if len(normalized.split()) >= MIN_AUTO_ALIAS_TOKENS:
                return mapping(
                    alias.canonical_name,
                    "alias_match",
                    self.settings.alias_threshold,
                    "AUTO_MATCHED",
                    f"alias of {alias.canonical_name}",
                )
            return mapping(
                alias.canonical_name,
                "alias_match",
                self.settings.alias_threshold,
                "REVIEW_REQUIRED",
                f"single-token alias of {alias.canonical_name} is ambiguous; manual review needed",
            )

        domain = domain_of(source_url)
        if (
            domain
            and not is_shared_domain(domain)
            and domain in self._startup_by_domain
        ):
            by_domain = self._startup_by_domain[domain]
            if by_domain is not None:
                return mapping(
                    by_domain.canonical_name,
                    "domain_match",
                    self.settings.domain_threshold,
                    "AUTO_MATCHED",
                    f"product domain {domain} matches startup website",
                )

        if not self._is_name_like(raw_name):
            return mapping(
                None,
                "not_name_like",
                0,
                "NO_MATCH",
                "descriptive title rather than a canonical entity name; fuzzy matching skipped",
            )

        if self._startup_keys:
            match = process.extractOne(key, self._startup_keys, scorer=fuzz.token_set_ratio, score_cutoff=0)
            if match is not None:
                _, score, index = match
                candidate = self.startups[index]
                length_ratio = min(len(key), len(candidate.name_key)) / max(len(key), len(candidate.name_key))
                character_ratio = fuzz.ratio(key, candidate.name_key)
                if (
                    score >= self.settings.auto_merge_threshold
                    and length_ratio >= self.settings.min_auto_length_ratio
                    and character_ratio >= self.settings.min_auto_character_ratio
                ):
                    return mapping(
                        candidate.canonical_name,
                        "fuzzy_token_set",
                        score,
                        "AUTO_MATCHED",
                        f"fuzzy token score {score:.1f}, character ratio {character_ratio:.1f}, length ratio {length_ratio:.2f}",
                    )
                if score >= self.settings.review_threshold:
                    return mapping(
                        candidate.canonical_name,
                        "fuzzy_token_set",
                        score,
                        "REVIEW_REQUIRED",
                        f"ambiguous fuzzy score {score:.1f} (character {character_ratio:.1f}, length {length_ratio:.2f}); manual review needed",
                    )
                best_score = score
                best_candidate = candidate.canonical_name
            else:
                best_score = 0.0
                best_candidate = None
        else:
            best_score = 0.0
            best_candidate = None

        seed = self._seed_by_key.get(key)
        if seed is not None:
            return mapping(
                seed.canonical_name,
                "seed_exact",
                100.0,
                "REVIEW_REQUIRED",
                "matched the seed list only; seed entries are not dataset records",
            )

        if normalized and best_candidate:
            return mapping(
                None,
                "fuzzy_token_set",
                best_score,
                "NO_MATCH",
                f"below review threshold; best candidate was {best_candidate}",
            )
        return mapping(None, "no_candidate", 0, "NO_MATCH", "no startup candidate resembled this name")

    def _is_name_like(self, raw_name: str) -> bool:
        key = name_key(raw_name)
        tokens = key.split()
        return (
            bool(key)
            and len(raw_name) <= self.settings.name_max_chars
            and 1 <= len(tokens) <= self.settings.name_max_tokens
        )

    def resolve_products(self) -> ResolveStats:
        stats = ResolveStats(methods={})
        products = self.db.fetch_records("PRODUCT")
        stats.products_total = len(products)
        assert stats.methods is not None

        # Associations are derived state: clear them before re-resolving so a
        # stricter run cannot leave stale auto-merges behind.
        for product in products:
            if product.get("content", {}).get("startupName") is not None:
                product["content"]["startupName"] = None
                self.db.upsert_records([product])

        for product in products:
            content = product.get("content", {})
            raw_name = str(content.get("entityName") or "")
            source_url = str(content.get("productUrl") or product.get("provenance", {}).get("recordUrl") or "")
            decision = self.resolve(raw_name, source_url)
            self.db.upsert_mapping(decision)
            stats.methods[decision.method] = stats.methods.get(decision.method, 0) + 1

            if decision.decision == "AUTO_MATCHED":
                stats.auto_matched += 1
                if decision.canonical_name and content.get("startupName") != decision.canonical_name:
                    content["startupName"] = decision.canonical_name
                    self.db.upsert_records([product])
                    stats.product_records_updated += 1
            elif decision.decision == "REVIEW_REQUIRED":
                stats.review_required += 1
            else:
                stats.no_match += 1

        self.log.info("entity resolution finished", extra={"count": stats.products_total})
        return stats
