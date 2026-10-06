"""Typed application configuration.

Values come from ``config/application.yml`` with environment overrides. The SEC
user agent is read from ``SEC_USER_AGENT`` and is never logged or persisted.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

EXAMPLE_UA_MARKERS = ("example.com", "your-monitored-email", "monitored-mailbox@example")
_EMAIL_RE = re.compile(r"[^@\s<>]+@[^@\s<>]+\.[A-Za-z]{2,}")


class SecConfig(BaseModel):
    user_agent: str | None = Field(default=None, repr=False, exclude=False)
    request_delay_seconds: float = 0.20
    request_timeout_seconds: float = 90
    retries: int = 4
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 30.0
    base_archive_url: str = "https://www.sec.gov/Archives/edgar/data"
    submissions_url: str = "https://data.sec.gov/submissions"

    @field_validator("request_delay_seconds")
    @classmethod
    def _min_delay(cls, v: float) -> float:
        # SEC fair-access guidance: no more than 10 requests/second.
        return max(v, 0.1)


class FilingsConfig(BaseModel):
    months_back: int = 18
    eligible_forms: list[str] = Field(default_factory=lambda: ["10-Q"])
    use_amendments: bool = False


class PathsConfig(BaseModel):
    cache: str = "./cache"
    templates: str = "./templates"
    output: str = "./output"
    golden: str = "./golden"


class ExtractionConfig(BaseModel):
    append_unmatched_html_rows: bool = True
    write_long_xbrl_facts: bool = True
    preserve_raw_values: bool = True
    excel_long_facts: bool = False
    offline: bool = False


class MatchingConfig(BaseModel):
    minimum_score: float = 5
    require_unique_best_match: bool = True
    minimum_margin: float = 1.0


class ValidationConfig(BaseModel):
    total_relative_tolerance: float = 0.005
    total_absolute_tolerance: float = 1.0
    spread_min: float = 0.0
    spread_max: float = 0.30
    allow_negative_fair_value: bool = False
    low_confidence_threshold: float = 0.5
    max_unmatched_html_ratio: float = 0.25
    max_conflict_ratio: float = 0.10
    min_axis_members: int = 3
    expected_currencies: list[str] = Field(default_factory=lambda: ["USD"])


class AppConfig(BaseModel):
    sec: SecConfig = Field(default_factory=SecConfig)
    filings: FilingsConfig = Field(default_factory=FilingsConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    matching: MatchingConfig = Field(default_factory=MatchingConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    source_path: str | None = None

    def resolve(self, name: str) -> Path:
        """Resolve a configured path relative to the config file directory (or CWD)."""
        raw = getattr(self.paths, name)
        p = Path(raw).expanduser()
        if p.is_absolute():
            return p
        base = Path(self.source_path).parent.parent if self.source_path else Path.cwd()
        return (base / p).resolve()

    def checksum(self) -> str:
        """Checksum of the effective configuration, excluding secrets."""
        data = self.model_dump(mode="json")
        data["sec"]["user_agent"] = "<redacted>"
        data.pop("source_path", None)
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


def is_genuine_user_agent(ua: str | None) -> bool:
    """A usable SEC user agent names an organization and a monitored email, and is not the example."""
    if not ua:
        return False
    lowered = ua.lower()
    if any(marker in lowered for marker in EXAMPLE_UA_MARKERS):
        return False
    if not _EMAIL_RE.search(ua):
        return False
    return len(ua.split()) >= 2


def load_config(path: str | Path | None = None, overrides: dict[str, Any] | None = None) -> AppConfig:
    """Load configuration from YAML, then apply environment and explicit overrides."""
    data: dict[str, Any] = {}
    cfg_path: Path | None = None
    if path is not None:
        cfg_path = Path(path)
    else:
        candidate = Path.cwd() / "config" / "application.yml"
        if candidate.exists():
            cfg_path = candidate
    if cfg_path is not None and cfg_path.exists():
        with cfg_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    # Environment overrides.
    env_ua = os.environ.get("SEC_USER_AGENT")
    if env_ua:
        data.setdefault("sec", {})["user_agent"] = env_ua
    for env_name, section, key in (
        ("BDC_SOI_CACHE", "paths", "cache"),
        ("BDC_SOI_OUTPUT", "paths", "output"),
        ("BDC_SOI_TEMPLATES", "paths", "templates"),
    ):
        val = os.environ.get(env_name)
        if val:
            data.setdefault(section, {})[key] = val
    if os.environ.get("BDC_SOI_OFFLINE") in {"1", "true", "TRUE", "yes"}:
        data.setdefault("extraction", {})["offline"] = True
    for dotted, value in (overrides or {}).items():
        section, key = dotted.split(".", 1)
        data.setdefault(section, {})[key] = value
    cfg = AppConfig.model_validate(data)
    cfg.source_path = str(cfg_path) if cfg_path else None
    return cfg
