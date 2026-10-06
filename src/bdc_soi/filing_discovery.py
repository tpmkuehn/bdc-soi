"""Filing discovery from SEC submissions JSON (SPEC 10.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from bdc_soi.config import FilingsConfig
from bdc_soi.models import FilingRecord
from bdc_soi.sec_client import (
    SecClient,
    is_illustrative_accession,
    normalize_accession,
    normalize_cik,
    pad_cik,
    submissions_file_url,
    submissions_url,
)

SUBMISSIONS_MAX_AGE_SECONDS = 24 * 3600


@dataclass
class DiscoveryResult:
    cik: str
    company_name: str | None
    filings: list[FilingRecord]
    selected: FilingRecord | None
    source_files: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_submissions_block(cik: str, company_name: str | None, block: dict[str, Any], source_file: str) -> list[FilingRecord]:
    """Convert the columnar ``filings.recent`` / older-file structure into records."""
    cols = {k: block.get(k, []) for k in ("accessionNumber", "filingDate", "reportDate", "form", "primaryDocument", "isXBRL", "isInlineXBRL")}
    n = len(cols["accessionNumber"])
    out: list[FilingRecord] = []
    for i in range(n):
        def col(name: str) -> Any:
            vals = cols[name]
            return vals[i] if i < len(vals) else None

        out.append(
            FilingRecord(
                cik=cik,
                company_name=company_name,
                accession_number=normalize_accession(col("accessionNumber")),
                form=str(col("form") or ""),
                filing_date=_parse_date(col("filingDate")),
                report_date=_parse_date(col("reportDate")),
                primary_document=col("primaryDocument"),
                is_xbrl=bool(col("isXBRL")) if col("isXBRL") is not None else None,
                is_inline_xbrl=bool(col("isInlineXBRL")) if col("isInlineXBRL") is not None else None,
                source_file=source_file,
            )
        )
    return out


def classify_filings(filings: list[FilingRecord], cfg: FilingsConfig, today: date) -> list[FilingRecord]:
    """Mark eligibility and reasons; select the latest eligible filing (10.1 steps 4-7)."""
    cutoff = today - timedelta(days=int(cfg.months_back * 30.44))
    eligible_forms = set(cfg.eligible_forms)
    if cfg.use_amendments:
        eligible_forms |= {f + "/A" for f in cfg.eligible_forms}
    for f in filings:
        reasons: list[str] = []
        if f.form not in eligible_forms:
            if f.form.endswith("/A") and f.form[:-2] in cfg.eligible_forms:
                reasons.append("amendment_excluded")
            else:
                reasons.append(f"form_not_eligible:{f.form}")
        if f.filing_date is None:
            reasons.append("missing_filing_date")
        elif f.filing_date < cutoff:
            reasons.append(f"older_than_lookback:{cutoff.isoformat()}")
        if is_illustrative_accession(f.accession_number):
            reasons.append("illustrative_accession")
        f.eligible = not reasons
        f.reason = "eligible" if f.eligible else ";".join(reasons)
        f.selected = False
    eligible = [f for f in filings if f.eligible]
    if eligible:
        best = max(eligible, key=lambda f: (f.filing_date or date.min, f.accession_number))
        best.selected = True
        best.reason = "selected_latest_eligible"
    return filings


def discover_filings(client: SecClient, cik: str | int, cfg: FilingsConfig, today: date | None = None) -> DiscoveryResult:
    cik = normalize_cik(cik)
    today = today or date.today()
    sub_dir = client.cache_dir / "sec" / "submissions"
    main_name = f"CIK{pad_cik(cik)}.json"
    data, res = client.fetch_json(submissions_url(cik, client.config.submissions_url), sub_dir / main_name, max_age_seconds=SUBMISSIONS_MAX_AGE_SECONDS)
    company_name = data.get("name")
    notes = [f"submissions:{'cache' if res.from_cache else 'network'}"]
    filings = parse_submissions_block(cik, company_name, data.get("filings", {}).get("recent", {}), main_name)
    sources = [main_name]
    cutoff = today - timedelta(days=int(cfg.months_back * 30.44))
    for extra in data.get("filings", {}).get("files", []) or []:
        name = extra.get("name")
        to_date = _parse_date(extra.get("filingTo"))
        if not name or (to_date is not None and to_date < cutoff):
            continue
        extra_data, _ = client.fetch_json(submissions_file_url(name, client.config.submissions_url), sub_dir / name, max_age_seconds=SUBMISSIONS_MAX_AGE_SECONDS)
        filings.extend(parse_submissions_block(cik, company_name, extra_data, name))
        sources.append(name)
    classify_filings(filings, cfg, today)
    selected = next((f for f in filings if f.selected), None)
    return DiscoveryResult(cik, company_name, filings, selected, sources, notes)


def find_filing(client: SecClient, cik: str | int, accession: str, cfg: FilingsConfig, today: date | None = None) -> tuple[FilingRecord | None, DiscoveryResult]:
    """Locate metadata for a specific accession (eligibility is informational here)."""
    result = discover_filings(client, cik, cfg, today)
    acc = normalize_accession(accession)
    rec = next((f for f in result.filings if f.accession_number == acc), None)
    for f in result.filings:
        f.selected = f.accession_number == acc
        if f.selected:
            f.reason = "selected_by_accession"
    result.selected = rec
    return rec, result
