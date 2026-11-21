"""Async HTTP client with bounded concurrency, pacing, retries and raw retention.

Error semantics implemented here:
* 429 -> honour Retry-After, exponential backoff with jitter, then retry.
* 413 -> raise PayloadTooLargeError so the caller can chunk its payload.
* 401/403 -> raise AccessBlockedError; the collector stops and records the
  source failure instead of attempting to bypass the restriction.
* 5xx / 408 / network errors -> bounded retries with backoff.
* 4xx -> fail fast (no pointless retries).
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import urlsplit

import aiohttp

from .config import HttpSettings
from .logging import get_logger
from .text import sha256_hex


class HttpError(Exception):
    def __init__(self, url: str, status: int, message: str = "") -> None:
        super().__init__(f"HTTP {status} for {url}: {message}".strip())
        self.url = url
        self.status = status
        self.message = message


class RetryableHttpError(HttpError):
    pass


class RateLimitedError(RetryableHttpError):
    def __init__(self, url: str, status: int, retry_after: float | None = None) -> None:
        super().__init__(url, status, "rate limited")
        self.retry_after = retry_after


class PayloadTooLargeError(HttpError):
    pass


class AccessBlockedError(HttpError):
    pass


class NetworkError(RetryableHttpError):
    def __init__(self, url: str, message: str) -> None:
        super().__init__(url, 0, message)


@dataclass
class HttpResponse:
    url: str
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    def text(self) -> str:
        content_type = self.headers.get("content-type", "text/plain")
        charset = "utf-8"
        for part in content_type.split(";")[1:]:
            part = part.strip()
            if part.lower().startswith("charset="):
                charset = part.split("=", 1)[1].strip().strip('"')
        try:
            return self.body.decode(charset, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text())


class _DomainLimiter:
    """Bounds per-domain concurrency and enforces a minimum request interval."""

    def __init__(self, concurrency: int, min_interval: float) -> None:
        self._semaphore = asyncio.Semaphore(max(1, concurrency))
        self._min_interval = max(0.0, min_interval)
        self._pacing_lock = asyncio.Lock()
        self._next_allowed = 0.0

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[None]:
        await self._semaphore.acquire()
        try:
            async with self._pacing_lock:
                current = time.monotonic()
                delay = max(0.0, self._next_allowed - current)
                self._next_allowed = max(current, self._next_allowed) + self._min_interval
            if delay:
                await asyncio.sleep(delay)
            yield
        finally:
            self._semaphore.release()


def _parse_retry_after(headers: dict[str, str]) -> float | None:
    value = headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value.strip()))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


class AsyncHttpClient:
    def __init__(
        self,
        http: HttpSettings,
        *,
        raw_dir: Path | None = None,
        source_tag: str | None = None,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._http = http
        self._raw_dir = raw_dir
        self._source_tag = source_tag or "unknown"
        self._session = session
        self._owns_session = session is None
        self._limiters: dict[str, _DomainLimiter] = {}
        self._penalty_until: dict[str, float] = {}
        self.log = get_logger("http")
        self.raw_files: list[str] = []

    async def __aenter__(self) -> "AsyncHttpClient":
        self._ensure_session()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(
                total=self._http.timeout_seconds,
                connect=self._http.connect_timeout_seconds,
            )
            connector = aiohttp.TCPConnector(
                limit=self._http.global_concurrency,
                limit_per_host=self._http.per_domain_concurrency,
                ttl_dns_cache=300,
            )
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={"User-Agent": self._http.user_agent, "Accept-Encoding": "gzip, deflate"},
            )
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed and self._owns_session:
            await self._session.close()
        self._session = None

    def _limiter(self, host: str) -> _DomainLimiter:
        limiter = self._limiters.get(host)
        if limiter is None:
            limiter = _DomainLimiter(
                self._http.per_domain_concurrency,
                self._http.min_interval_for(host),
            )
            self._limiters[host] = limiter
        return limiter

    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        retries: int | None = None,
        raw_label: str | None = None,
        allow_status: tuple[int, ...] = (),
    ) -> HttpResponse:
        return await self.request(
            "GET",
            url,
            params=params,
            headers=headers,
            retries=retries,
            raw_label=raw_label,
            allow_status=allow_status,
        )

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        retries: int | None = None,
        raw_label: str | None = None,
        allow_status: tuple[int, ...] = (),
        json_body: Any | None = None,
    ) -> HttpResponse:
        session = self._ensure_session()
        host = urlsplit(url).hostname or ""
        max_attempts = max(1, (self._http.max_retries if retries is None else retries) + 1)

        for attempt in range(max_attempts):
            penalty = self._penalty_until.get(host, 0.0)
            if penalty > time.monotonic():
                await asyncio.sleep(penalty - time.monotonic())
            try:
                response = await self._request_once(session, method, url, params, headers, allow_status, json_body)
                if raw_label:
                    self._save_raw(raw_label, response)
                return response
            except RateLimitedError as exc:
                backoff = self._backoff(attempt)
                wait = exc.retry_after if exc.retry_after is not None else backoff
                wait = min(max(wait, 0.0), self._http.max_backoff_seconds)
                self._penalty_until[host] = time.monotonic() + wait
                self.log.warning(
                    "rate limited", extra={"url": url, "status": 429, "attempt": attempt + 1, "source": host}
                )
                if attempt + 1 >= max_attempts:
                    raise
                await asyncio.sleep(wait + random.uniform(0, 0.5))
            except PayloadTooLargeError:
                raise
            except AccessBlockedError:
                raise
            except RetryableHttpError as exc:
                if attempt + 1 >= max_attempts:
                    raise
                wait = min(self._backoff(attempt), self._http.max_backoff_seconds)
                self.log.warning(
                    "retrying request",
                    extra={"url": url, "status": exc.status, "attempt": attempt + 1, "source": host},
                )
                await asyncio.sleep(wait + random.uniform(0, 0.25))
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt + 1 >= max_attempts:
                    raise NetworkError(url, f"{type(exc).__name__}: {exc}") from exc
                wait = min(self._backoff(attempt), self._http.max_backoff_seconds)
                self.log.warning(
                    "network error, retrying",
                    extra={"url": url, "attempt": attempt + 1, "source": host},
                )
                await asyncio.sleep(wait + random.uniform(0, 0.25))

        raise NetworkError(url, "retry budget exhausted")

    async def _request_once(
        self,
        session: aiohttp.ClientSession,
        method: str,
        url: str,
        params: dict[str, Any] | None,
        headers: dict[str, str] | None,
        allow_status: tuple[int, ...],
        json_body: Any | None = None,
    ) -> HttpResponse:
        host = urlsplit(url).hostname or ""
        async with self._limiter(host).acquire():
            try:
                async with session.request(
                    method, url, params=params, headers=headers, json=json_body, allow_redirects=True
                ) as response:
                    body = await response.read()
                    status = response.status
                    response_headers = {k.lower(): v for k, v in response.headers.items()}
                    final_url = str(response.url)
            except (aiohttp.ClientError, asyncio.TimeoutError):
                raise

        result = HttpResponse(url=final_url, status=status, headers=response_headers, body=body)

        if status == 429:
            raise RateLimitedError(final_url, status, _parse_retry_after(response_headers))
        if status == 413:
            raise PayloadTooLargeError(final_url, status, "payload too large")
        if status in (401, 403):
            raise AccessBlockedError(final_url, status, "access restricted")
        if status == 408 or status >= 500:
            raise RetryableHttpError(final_url, status, "transient server failure")
        if status >= 400 and status not in allow_status:
            raise HttpError(final_url, status, "unexpected response")
        return result

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        response = await self.get(url, **kwargs)
        return response.json()

    async def post_json(
        self,
        url: str,
        *,
        json_body: Any,
        headers: dict[str, str] | None = None,
        retries: int | None = None,
        raw_label: str | None = None,
        allow_status: tuple[int, ...] = (),
    ) -> HttpResponse:
        return await self.request(
            "POST",
            url,
            json_body=json_body,
            headers=headers,
            retries=retries,
            raw_label=raw_label,
            allow_status=allow_status,
        )

    async def get_text(self, url: str, **kwargs: Any) -> str:
        response = await self.get(url, **kwargs)
        return response.text()

    def _backoff(self, attempt: int) -> float:
        base = self._http.base_backoff_seconds * (2**attempt)
        return min(base * (1 + random.uniform(0, 0.5)), self._http.max_backoff_seconds)

    def _save_raw(self, label: str, response: HttpResponse) -> None:
        if self._raw_dir is None:
            return
        try:
            directory = Path(self._raw_dir) / self._source_tag
            directory.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
            digest = sha256_hex(response.body)[:12]
            content_type = response.headers.get("content-type", "")
            extension = "json" if "json" in content_type else "xml" if "xml" in content_type or "atom" in content_type else "txt"
            path = directory / f"{stamp}-{label}-{digest}.{extension}"
            path.write_bytes(response.body)
            self.raw_files.append(str(path))
        except OSError as exc:  # raw retention must never break collection
            self.log.warning("failed to persist raw response: %s", exc, extra={"source": self._source_tag})
