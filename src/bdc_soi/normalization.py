"""Generic normalization: text, numbers, percentages, rates, dates (SPEC 12.7, 13.3, 13.5)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from bdc_soi.models import BOOLEAN_FIELDS, COUNT_FIELDS, DATE_FIELDS, MONETARY_FIELDS, PROPORTION_FIELDS, RATE_FIELDS
from bdc_soi.templates import LegalSuffixes

LEGAL_SUFFIXES = (
    "LLC", "L.L.C.", "Inc", "Inc.", "Corp", "Corp.", "Corporation", "Ltd", "Ltd.", "Limited", "LP", "L.P.", "LLP",
    "L.L.P.", "Co", "Co.", "plc", "PLC", "S.A.", "SA", "S.à r.l.", "S.a r.l.", "SARL", "GmbH", "B.V.", "BV", "N.V.",
    "NV", "AG", "Pty", "Pty.", "Holdings", "Company", "Incorporated", "ULC", "S.p.A.", "SpA", "AB", "AS", "A/S", "Oy",
    "KK", "S.A.S.", "SAS", "SE", "LTD", "INC", "CORP",
)
_SUFFIX_RE = re.compile(r",\s+(?=(?:" + "|".join(re.escape(s) for s in sorted(LEGAL_SUFFIXES, key=len, reverse=True)) + r")\b)")
_WS_RE = re.compile(r"\s+")
_DASHES = {"—", "–", "-", "‒", "―", "−", "- -"}
_FOOTNOTE_RE = re.compile(r"\s*(?:\(\s*[a-z0-9]{1,3}\s*\)|\[\s*[a-z0-9]{1,3}\s*\]|\*+|†|‡|§)\s*$", re.IGNORECASE)
_LEADING_FOOTNOTE_RE = re.compile(r"^\s*(?:\(\s*[a-z0-9]{1,3}\s*\)\s*)+", re.IGNORECASE)
_NUM_RE = re.compile(r"^[\s$€£¥]*(?P<open>\()?\s*[\s$€£¥]*(?P<num>-?\d[\d,]*(?:\.\d+)?|-?\.\d+)\s*(?P<unit_in>%|bps|bp|basis points|x)?\s*(?P<close>\))?\s*(?P<unit>%|bps|bp|basis points|x)?\s*$", re.IGNORECASE)


@dataclass
class ParsedNumber:
    value: float | None
    kind: str  # number | percent | bps | null | text | multiple
    raw: str
    negative: bool = False
    footnotes: str | None = None
    note: str | None = None


_INVISIBLE_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")


def collapse_ws(text: str) -> str:
    return _WS_RE.sub(" ", _INVISIBLE_RE.sub("", text).replace("\xa0", " ")).strip()


def normalize_issuer(text: str | None, rules: LegalSuffixes | None = None) -> str | None:
    if text is None:
        return None
    rules = rules or LegalSuffixes()
    t = collapse_ws(text)
    t = _LEADING_FOOTNOTE_RE.sub("", t)
    t = strip_footnote_markers(t)[0]
    if rules.remove_preceding_comma:
        t = _SUFFIX_RE.sub(" ", t)
    if rules.strip_trailing_period and t.endswith(".") and not re.search(r"\b[A-Z]\.$", t):
        t = t[:-1]
    return collapse_ws(t) or None


def normalize_description(text: str | None) -> str | None:
    if text is None:
        return None
    t = collapse_ws(text)
    t = strip_footnote_markers(t)[0]
    return t or None


def text_key(text: str | None) -> str:
    """Case- and punctuation-insensitive comparison key."""
    if not text:
        return ""
    t = text.lower().replace("&", " and ")
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return collapse_ws(t)


def strip_footnote_markers(text: str) -> tuple[str, str | None]:
    markers: list[str] = []
    t = text.strip()
    while True:
        m = _FOOTNOTE_RE.search(t)
        if not m or m.start() == 0:
            break
        markers.insert(0, m.group(0).strip())
        t = t[: m.start()].rstrip()
    return t, (" ".join(markers) if markers else None)


_ISO_CODE_RE = re.compile(r"^(?:C\$|A\$|NZ\$|S\$|HK\$|US\$|CAD|AUD|EUR|GBP|USD|CHF|NOK|SEK|DKK)(?=\s|$)|(?<=\s)(?:CAD|AUD|EUR|GBP|USD|CHF|NOK|SEK|DKK)$")


def parse_number(text: str | None) -> ParsedNumber:
    """Parse a monetary/numeric cell: currency symbols, commas, parentheses negatives, dashes as null."""
    if text is None:
        return ParsedNumber(None, "null", "", note="none")
    raw = text
    t = collapse_ws(text)
    if _ISO_CODE_RE.search(t) and _ISO_CODE_RE.sub("", t).strip():
        t = _ISO_CODE_RE.sub("", t).strip()  # 'CHF 19,009' / '19,009 EUR': the code is currency evidence, not text
    if t == "" or t in _DASHES or re.fullmatch(r"[\s$€£¥]*[—–\-−]+[\s$€£¥]*", t):
        return ParsedNumber(None, "null", raw)
    footnotes: str | None = None
    stripped = t.replace("$", "").replace("€", "").replace("£", "").strip()
    m = _NUM_RE.match(stripped)
    if not m:
        # Strip trailing footnote markers only when what remains is itself a number.
        t2, footnotes = strip_footnote_markers(t)
        t2 = t2.replace("$", "").replace("€", "").replace("£", "").strip()
        if t2 == "" or t2 in _DASHES:
            return ParsedNumber(None, "null", raw, footnotes=footnotes)
        m = _NUM_RE.match(t2)
        if not m:
            return ParsedNumber(None, "text", raw, footnotes=footnotes)
    num = m.group("num").replace(",", "")
    negative = bool(m.group("open") and m.group("close"))
    try:
        value = float(num)
    except ValueError:
        return ParsedNumber(None, "text", raw, footnotes=footnotes)
    if negative:
        value = -abs(value)
    unit = (m.group("unit") or m.group("unit_in") or "").lower()
    if unit == "%":
        return ParsedNumber(value, "percent", raw, negative, footnotes)
    if unit in {"bps", "bp", "basis points"}:
        return ParsedNumber(value, "bps", raw, negative, footnotes)
    if unit == "x":
        return ParsedNumber(value, "multiple", raw, negative, footnotes)
    return ParsedNumber(value, "number", raw, negative, footnotes)


def percent_to_decimal(value: float) -> float:
    return round(value / 100.0, 10)


def bps_to_decimal(value: float) -> float:
    return round(value / 10000.0, 10)


def decimal_to_bps(value: float) -> float:
    return round(value * 10000.0, 6)


def parse_date(text: str | None, formats: list[str] | None = None) -> tuple[date | None, str | None]:
    """Normalize to ISO date; ambiguous/invalid values return (None, diagnostic)."""
    if text is None:
        return None, "empty"
    t = collapse_ws(str(text))
    t = strip_footnote_markers(t)[0]
    if not t or t in _DASHES or t.upper() in {"N/A", "NA", "N.A.", "NONE", "NM"}:
        return None, "empty"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
        try:
            return datetime.strptime(t, "%Y-%m-%d").date(), None
        except ValueError:
            return None, f"invalid_iso_date:{t}"
    fmts = list(formats or ["%m/%d/%Y", "%Y-%m-%d"])
    for extra in ("%m/%d/%y", "%B %d, %Y", "%b %d, %Y", "%d-%b-%Y", "%m/%Y", "%B %Y", "%b %Y"):
        if extra not in fmts:
            fmts.append(extra)
    candidates: list[date] = []
    for fmt in fmts:
        try:
            candidates.append(datetime.strptime(t, fmt).date())
        except ValueError:
            continue
    uniq = sorted(set(candidates))
    if len(uniq) == 1:
        return uniq[0], None
    if len(uniq) > 1:
        return None, f"ambiguous_date:{t}"
    return None, f"unparsed_date:{t}"


def coerce_value(field: str, value: Any, date_formats: list[str] | None = None) -> tuple[Any, str | None]:
    """Coerce a raw value to the canonical type for ``field``. Returns (value, diagnostic)."""
    if value is None:
        return None, None
    if field in DATE_FIELDS:
        if isinstance(value, date):
            return value, None
        if isinstance(value, datetime):
            return value.date(), None
        return parse_date(str(value), date_formats)
    if field in MONETARY_FIELDS or field in COUNT_FIELDS:
        if isinstance(value, (int, float)):
            return float(value), None
        p = parse_number(str(value))
        return p.value, (None if p.value is not None else f"unparsed_number:{p.raw}")
    if field in RATE_FIELDS or field in PROPORTION_FIELDS:
        if isinstance(value, (int, float)):
            return float(value), None
        p = parse_number(str(value))
        if p.value is None:
            return (str(value) if field == "interest_rate" else None), f"unparsed_rate:{p.raw}"
        if p.kind == "percent":
            return (percent_to_decimal(p.value) if field != "spread_bps" else p.value * 100.0), None
        if p.kind == "bps":
            return (bps_to_decimal(p.value) if field != "spread_bps" else p.value), None
        return p.value, None
    if field in BOOLEAN_FIELDS:
        if isinstance(value, bool):
            return value, None
        s = str(value).strip().lower()
        if s in {"true", "yes", "1"}:
            return True, None
        if s in {"false", "no", "0"}:
            return False, None
        return None, f"unparsed_boolean:{value}"
    s = collapse_ws(str(value))
    return (s or None), None
