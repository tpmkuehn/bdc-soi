"""SEC EDGAR HTTP client: compliant user agent, shared rate limiting, bounded retries, caching (SPEC 4.3).

The user agent is never logged. Failed requests are logged with URL, status and attempt only.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from bdc_soi.config import SecConfig, is_genuine_user_agent

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 500, 502, 503, 504}
_ACCESSION_RE = re.compile(r"^(\d{10})-?(\d{2})-?(\d{6})$")


class SecClientError(RuntimeError):
    pass


class UserAgentError(SecClientError):
    pass


class OfflineCacheMiss(SecClientError):
    pass


# ---------------------------------------------------------------------------
# Identifiers and URLs (SPEC 7.2, 10)
# ---------------------------------------------------------------------------


def normalize_cik(value: str | int) -> str:
    s = str(value).strip()
    if not s.isdigit():
        raise ValueError(f"invalid CIK: {value!r}")
    return s.lstrip("0") or "0"


def pad_cik(value: str | int) -> str:
    return normalize_cik(value).zfill(10)


def normalize_accession(value: str) -> str:
    """Return dashed form ``0001234567-25-000123``."""
    m = _ACCESSION_RE.match(str(value).strip())
    if not m:
        raise ValueError(f"invalid accession number: {value!r}")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def accession_nodash(value: str) -> str:
    return normalize_accession(value).replace("-", "")


def is_illustrative_accession(value: str) -> bool:
    """SPEC example accessions (filer prefix all zeros) are illustrative and must never be fetched."""
    try:
        return normalize_accession(value).startswith("0000000000-")
    except ValueError:
        return False


def submissions_url(cik: str | int, base: str = "https://data.sec.gov/submissions") -> str:
    return f"{base}/CIK{pad_cik(cik)}.json"


def submissions_file_url(name: str, base: str = "https://data.sec.gov/submissions") -> str:
    return f"{base}/{name}"


def accession_dir_url(cik: str | int, accession: str, base: str = "https://www.sec.gov/Archives/edgar/data") -> str:
    return f"{base}/{normalize_cik(cik)}/{accession_nodash(accession)}"


def accession_index_url(cik: str | int, accession: str, base: str = "https://www.sec.gov/Archives/edgar/data") -> str:
    return f"{accession_dir_url(cik, accession, base)}/index.json"


def accession_file_url(cik: str | int, accession: str, filename: str, base: str = "https://www.sec.gov/Archives/edgar/data") -> str:
    return f"{accession_dir_url(cik, accession, base)}/{filename}"


# ---------------------------------------------------------------------------
# Shared rate limiter (process-wide, thread-safe)
# ---------------------------------------------------------------------------


class RateLimiter:
    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self, sleep=time.sleep, now=time.monotonic) -> float:
        with self._lock:
            t = now()
            delay = max(0.0, self._next_allowed - t)
            self._next_allowed = max(t, self._next_allowed) + self.min_interval
        if delay > 0:
            sleep(delay)
        return delay


_SHARED_LIMITERS: dict[float, RateLimiter] = {}
_SHARED_LOCK = threading.Lock()


def shared_rate_limiter(min_interval: float) -> RateLimiter:
    with _SHARED_LOCK:
        key = round(min_interval, 4)
        lim = _SHARED_LIMITERS.get(key)
        if lim is None:
            lim = RateLimiter(min_interval)
            _SHARED_LIMITERS[key] = lim
        return lim


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


@dataclass
class FetchResult:
    url: str
    local_path: Path
    size: int
    sha256: str
    from_cache: bool
    content_type: str | None = None


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class SecClient:
    def __init__(
        self,
        config: SecConfig,
        cache_dir: Path,
        offline: bool = False,
        session: requests.Session | None = None,
        sleep=time.sleep,
    ):
        self.config = config
        self.cache_dir = Path(cache_dir)
        self.offline = offline
        self._session = session
        self._sleep = sleep
        self.limiter = shared_rate_limiter(config.request_delay_seconds)
        self.request_log: list[dict[str, Any]] = []

    # -- session -----------------------------------------------------------
    @property
    def session(self) -> requests.Session:
        if self._session is None:
            if not is_genuine_user_agent(self.config.user_agent):
                raise UserAgentError(
                    "SEC_USER_AGENT must name your organization and a genuine monitored email "
                    "(the example address is not accepted). Set it in the environment before live requests."
                )
            s = requests.Session()
            s.headers.update(
                {
                    "User-Agent": self.config.user_agent or "",
                    "Accept-Encoding": "gzip, deflate",
                    "Accept": "*/*",
                }
            )
            self._session = s
        return self._session

    # -- HTTP --------------------------------------------------------------
    def get_bytes(self, url: str) -> tuple[bytes, str | None]:
        if self.offline:
            raise OfflineCacheMiss(f"offline mode: refusing network request for {url}")
        attempts = self.config.retries + 1
        last_error: str | None = None
        for attempt in range(1, attempts + 1):
            self.limiter.wait(sleep=self._sleep)
            try:
                resp = self.session.get(url, timeout=self.config.request_timeout_seconds)
            except requests.RequestException as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                self._log_failure(url, None, attempt, last_error)
                self._backoff(attempt)
                continue
            if resp.status_code == 200:
                return resp.content, resp.headers.get("Content-Type")
            last_error = f"HTTP {resp.status_code}"
            self._log_failure(url, resp.status_code, attempt, last_error)
            if resp.status_code in RETRY_STATUSES and attempt < attempts:
                retry_after = resp.headers.get("Retry-After")
                self._backoff(attempt, retry_after)
                continue
            break
        raise SecClientError(f"request failed for {url}: {last_error}")

    def _backoff(self, attempt: int, retry_after: str | None = None) -> None:
        delay = min(self.config.backoff_max_seconds, self.config.backoff_base_seconds * (2 ** (attempt - 1)))
        if retry_after and retry_after.isdigit():
            delay = max(delay, float(retry_after))
        self._sleep(delay)

    def _log_failure(self, url: str, status: int | None, attempt: int, message: str) -> None:
        entry = {"url": url, "status": status, "attempt": attempt, "message": message}
        self.request_log.append(entry)
        log.warning("SEC request failed url=%s status=%s attempt=%s message=%s", url, status, attempt, message)

    # -- cache -------------------------------------------------------------
    def fetch_to_cache(self, url: str, local_path: Path, *, expected_size: int | None = None, max_age_seconds: float | None = None) -> FetchResult:
        """Download ``url`` to ``local_path`` unless an acceptable cached copy exists."""
        local_path = Path(local_path)
        if local_path.exists():
            size = local_path.stat().st_size
            fresh = True
            if expected_size is not None and size != expected_size:
                fresh = False
            if max_age_seconds is not None and (time.time() - local_path.stat().st_mtime) > max_age_seconds:
                fresh = False
            if fresh or self.offline:
                return FetchResult(url, local_path, size, sha256_of_file(local_path), True)
        if self.offline:
            raise OfflineCacheMiss(f"offline mode and no cached copy for {url} at {local_path}")
        content, ctype = self.get_bytes(url)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = local_path.with_suffix(local_path.suffix + ".part")
        tmp.write_bytes(content)
        tmp.replace(local_path)
        return FetchResult(url, local_path, len(content), hashlib.sha256(content).hexdigest(), False, ctype)

    def fetch_json(self, url: str, local_path: Path, max_age_seconds: float | None = None) -> tuple[dict[str, Any], FetchResult]:
        res = self.fetch_to_cache(url, local_path, max_age_seconds=max_age_seconds)
        with res.local_path.open("r", encoding="utf-8") as fh:
            return json.load(fh), res
