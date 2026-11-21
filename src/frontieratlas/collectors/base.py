"""Collector contracts shared by every source adapter."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..common.config import AppSettings
from ..common.http import AsyncHttpClient
from ..common.logging import get_logger
from ..storage.db import Database

MAX_REJECTION_DETAILS = 500


@dataclass
class Rejection:
    reason: str
    detail: str | None = None
    source_url: str | None = None


@dataclass
class CollectorOutput:
    source_name: str
    record_type: str
    records: list[dict] = field(default_factory=list)
    discovered: int = 0
    rejections: list[Rejection] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    source_meta: dict[str, Any] = field(default_factory=dict)

    @property
    def accepted(self) -> int:
        return len(self.records)

    @property
    def rejected(self) -> int:
        return max(self.discovered - self.accepted, len(self.rejections))

    def add_rejection(self, reason: str, detail: str | None = None, source_url: str | None = None) -> None:
        if len(self.rejections) < MAX_REJECTION_DETAILS:
            self.rejections.append(Rejection(reason=reason, detail=(detail or "")[:300] or None, source_url=source_url))


@dataclass
class CollectorContext:
    settings: AppSettings
    client: AsyncHttpClient
    db: Database
    now: datetime

    def checkpoint(self, key: str, default: Any = None) -> Any:
        return self.db.get_checkpoint(f"collector:{key}", default)

    def save_checkpoint(self, key: str, value: Any) -> None:
        self.db.set_checkpoint(f"collector:{key}", value)

    @property
    def max_age_hours(self) -> int:
        return self.settings.freshness.max_age_hours

    @property
    def clock_skew_minutes(self) -> int:
        return self.settings.freshness.clock_skew_minutes


class BaseCollector(ABC):
    name: str = "base"
    record_type: str = "UNKNOWN"
    source_url: str = ""
    source_meta: dict[str, Any] = {}

    def __init__(self) -> None:
        self.log = get_logger(f"collector.{self.name}")

    @abstractmethod
    async def collect(self, ctx: CollectorContext) -> CollectorOutput:
        raise NotImplementedError
