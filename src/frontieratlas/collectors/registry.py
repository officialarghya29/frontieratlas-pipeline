"""Collector registry: every enabled source is constructed from config/sources.yaml."""

from __future__ import annotations

from ..common.config import AppSettings
from .arxiv import ArxivCollector
from .base import BaseCollector
from .hfspaces import HuggingFaceSpacesCollector
from .jobs import (
    ArbeitnowCollector,
    HimalayasCollector,
    JobicyCollector,
    RemoteOKCollector,
    RemotiveCollector,
)
from .news import NewsSourceCollector
from .producthunt import ProductHuntCollector
from .showhn import ShowHNCollector
from .yc import YCStartupCollector

JOB_COLLECTORS: dict[str, type[BaseCollector]] = {
    "himalayas": HimalayasCollector,
    "remotive": RemotiveCollector,
    "remoteok": RemoteOKCollector,
    "arbeitnow": ArbeitnowCollector,
    "jobicy": JobicyCollector,
}


def build_collectors(settings: AppSettings) -> list[BaseCollector]:
    sources = settings.sources
    collectors: list[BaseCollector] = []

    for key, cfg in (sources.get("startups") or {}).items():
        if cfg.get("enabled") and key == "yc_ai":
            collectors.append(YCStartupCollector(cfg))

    for key, cfg in (sources.get("products") or {}).items():
        if not cfg.get("enabled"):
            continue
        if key == "producthunt":
            collectors.append(ProductHuntCollector(cfg))
        elif key == "showhn":
            collectors.append(ShowHNCollector(cfg))
        elif key == "huggingface_spaces":
            collectors.append(HuggingFaceSpacesCollector(cfg))

    for key, cfg in (sources.get("papers") or {}).items():
        if cfg.get("enabled") and key == "arxiv":
            collectors.append(ArxivCollector(cfg))

    for cfg in (sources.get("news") or {}).get("sources", []):
        if cfg.get("verified", True):
            collectors.append(NewsSourceCollector(cfg))

    for cfg in (sources.get("jobs") or {}).get("sources", []):
        if not cfg.get("verified", True):
            continue
        collector_cls = JOB_COLLECTORS.get(str(cfg.get("key")))
        if collector_cls:
            collectors.append(collector_cls(cfg))

    return collectors
