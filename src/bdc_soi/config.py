"""Typed application configuration.

Values come from ``config/application.yml`` with environment overrides. The SEC
user agent is resolved centrally by :func:`resolve_user_agent`: an explicit
``--sec-email`` (plus optional ``--sec-organization``) builds it from the
application name and version; otherwise an explicitly configured
``SEC_USER_AGENT`` environment variable is used as given. There is no built-in
contact default. The resolved value is never logged or persisted.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from bdc_soi import ENGINE_VERSION

APP_NAME = "bdc_soi"
EXAMPLE_UA_MARKERS = ("example.com", "your-monitored-email", "monitored-mailbox@example")
_EMAIL_RE = re.compile(r"[^@\s<>]+@[^@\s<>]+\.[A-Za-z]{2,}")
_EMAIL_EXACT_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,}$")
UserAgentSource = Literal["none", "config", "environment", "cli"]

USER_AGENT_SETUP_MESSAGE = (
    "Live SEC retrieval needs a monitored contact and none is configured. Either pass "
    "--sec-email <monitored address> (optionally --sec-organization \"<your organization>\") "
    "to extract, extract-universe or inspect, or export SEC_USER_AGENT=\"<Organization> <monitored address>\" "
    "in the shell before running. Placeholder addresses (example.com) are rejected. "
    "Cached filings can be processed without a contact by passing --offline."
)


class ContactEmailError(ValueError):
    """An explicitly supplied SEC contact is empty, malformed or a documentation placeholder."""


class SecConfig(BaseModel):
    user_agent: str | None = Field(default=None, repr=False, exclude=False)
    # Operational provenance only: where the user agent came from, never the value itself.
    user_agent_source: UserAgentSource = "none"
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
        data["sec"].pop("user_agent_source", None)  # provenance, not an effective setting
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


def validate_contact_email(value: str | None) -> str:
    """Return the normalized explicit contact email or raise :class:`ContactEmailError`.

    Rejects empty values, values with whitespace or angle brackets, anything that is not a
    single ``name@domain`` address, and the documentation placeholders.
    """
    if value is None or not str(value).strip():
        raise ContactEmailError("--sec-email was given without an address. " + USER_AGENT_SETUP_MESSAGE)
    email = str(value).strip()
    if not _EMAIL_EXACT_RE.match(email) or email.count("@") != 1:
        raise ContactEmailError(f"--sec-email {email!r} is not a valid email address (expected a single address in the form name@domain). " + USER_AGENT_SETUP_MESSAGE)
    lowered = email.lower()
    if any(marker in lowered for marker in EXAMPLE_UA_MARKERS):
        raise ContactEmailError(f"--sec-email {email!r} is a documentation placeholder; supply a genuine monitored address. " + USER_AGENT_SETUP_MESSAGE)
    return email


def validate_organization(value: str | None) -> str | None:
    """Normalize an optional organization name for the user agent (single line, no control characters)."""
    if value is None:
        return None
    org = " ".join(str(value).split())
    if not org:
        raise ContactEmailError("--sec-organization was given without a name.")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in org):
        raise ContactEmailError("--sec-organization must not contain control characters.")
    return org


def build_user_agent(email: str, organization: str | None = None) -> str:
    """Build the descriptive SEC user agent: ``[<organization>] bdc_soi/<version> <email>``."""
    email = validate_contact_email(email)
    org = validate_organization(organization)
    parts = [org] if org else []
    parts.append(f"{APP_NAME}/{ENGINE_VERSION}")
    parts.append(email)
    return " ".join(parts)


def resolve_user_agent(sec_email: str | None = None, organization: str | None = None, env: Mapping[str, str] | None = None) -> tuple[str | None, UserAgentSource]:
    """Resolve the SEC user agent and its provenance.

    Precedence: an explicitly supplied ``sec_email`` (validated, never silently ignored) builds the
    user agent; otherwise a non-empty ``SEC_USER_AGENT`` environment value is used as given; otherwise
    ``(None, "none")`` so that live retrieval fails before any request is made. ``organization`` is
    only meaningful together with ``sec_email``.
    """
    environ = os.environ if env is None else env
    if sec_email is not None:
        return build_user_agent(sec_email, organization), "cli"
    if organization is not None:
        raise ContactEmailError("--sec-organization requires --sec-email.")
    env_ua = environ.get("SEC_USER_AGENT")
    if env_ua and env_ua.strip():
        return env_ua.strip(), "environment"
    return None, "none"


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
    # Environment overrides. SEC_USER_AGENT takes precedence over a YAML value; an explicit
    # --sec-email arrives through ``overrides`` and takes precedence over both.
    sec_data = data.setdefault("sec", {}) or {}
    data["sec"] = sec_data
    env_ua, env_source = resolve_user_agent(env=os.environ)
    if env_ua:
        sec_data["user_agent"] = env_ua
        sec_data["user_agent_source"] = env_source
    elif sec_data.get("user_agent"):
        sec_data["user_agent_source"] = "config"
    else:
        sec_data["user_agent"] = None
        sec_data["user_agent_source"] = "none"
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
    if "sec.user_agent" in (overrides or {}):
        sec_data["user_agent_source"] = (overrides or {}).get("sec.user_agent_source", "cli")
    cfg = AppConfig.model_validate(data)
    cfg.source_path = str(cfg_path) if cfg_path else None
    return cfg
