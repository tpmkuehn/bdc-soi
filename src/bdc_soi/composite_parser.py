"""Composite text splitting with template-defined named-capture rules (SPEC 13)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from bdc_soi.normalization import bps_to_decimal, collapse_ws, normalize_description, normalize_issuer, parse_date, percent_to_decimal, text_key
from bdc_soi.templates import CompositeField, NormalizationSpec, RateParser

GENERIC_RATE_PATTERN = r"(?:\d+\s*M(?:onth)?\s+|\d+M\s+|Term\s+)?(?P<index>SOFR|LIBOR|Prime|PRIME|EURIBOR|SONIA|CDOR|BBSW|BBSY|BKBM|STIBOR|NIBOR|CORRA|TONAR|SORA|SARON|KORIBOR|ESTR|Base Rate)(?:\s*\([A-Z]\))?(?:\s*USD)?\s*\+\s*(?:CSA\s*\+\s*)?(?P<spread_bps>\d+(?:\.\d+)?)"
GENERIC_FLOOR_PATTERN = r"(?P<floor_pct>\d+(?:\.\d+)?)\s*%\s*(?:Floor|floor|FLOOR)"
GENERIC_PIK_PATTERN = r"(?P<pik_pct>\d+(?:\.\d+)?)\s*%\s*PIK"
GENERIC_CASH_PATTERN = r"(?P<cash_pct>\d+(?:\.\d+)?)\s*%\s*(?:Cash|cash)"
UNAMBIGUOUS_INDEX_ALIASES = {
    "SOFR": "SOFR", "TERM SOFR": "SOFR", "LIBOR": "LIBOR", "PRIME": "Prime", "EURIBOR": "EURIBOR", "SONIA": "SONIA",
    "CDOR": "CDOR", "BBSW": "BBSW", "STIBOR": "STIBOR", "NIBOR": "NIBOR", "CORRA": "CORRA", "TONAR": "TONAR", "SORA": "SORA",
    "BASE RATE": "Base Rate", "BKBM": "BKBM", "BBSY": "BBSY", "KORIBOR": "KORIBOR", "ESTR": "ESTR", "€STR": "ESTR", "SARON": "SARON", "TIIE": "TIIE", "JIBAR": "JIBAR", "HIBOR": "HIBOR", "TONA": "TONAR",
}


@dataclass
class ParsedField:
    field: str
    value: Any
    raw: str
    transformation: str


@dataclass
class CompositeResult:
    matched: bool
    rule_id: str | None
    fields: dict[str, ParsedField] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class RateResult:
    reference_index: str | None = None
    spread_bps: float | None = None
    spread: float | None = None
    rate_floor: float | None = None
    pik_rate: float | None = None
    cash_rate: float | None = None
    interest_rate: float | None = None
    raw: str = ""
    matched: bool = False
    diagnostics: list[str] = field(default_factory=list)
    spread_raw: str | None = None


def resolve_index(token: str | None, aliases: dict[str, str]) -> tuple[str | None, str | None]:
    if token is None:
        return None, None
    t = collapse_ws(token)
    if t in aliases:
        return aliases[t], f"alias:{t}"
    if t.upper() in {k.upper() for k in aliases}:
        for k, v in aliases.items():
            if k.upper() == t.upper():
                return v, f"alias:{k}"
    if t.upper() in UNAMBIGUOUS_INDEX_ALIASES:
        return UNAMBIGUOUS_INDEX_ALIASES[t.upper()], f"generic_alias:{t.upper()}"
    return None, f"unresolved_index:{t}"


def _spread_from_match(m: re.Match[str], text: str, unit_setting: str, diags: list[str]) -> tuple[float | None, float | None, str | None]:
    """Return (spread_bps, spread_decimal, raw). Percent-formatted spreads never flow through the bps branch."""
    gd = m.groupdict()
    raw_num: str | None = None
    unit: str | None = None
    for name in ("spread_pct", "spread_bps", "spread"):
        if gd.get(name) is not None:
            raw_num = gd[name]
            unit = {"spread_pct": "percent", "spread_bps": "basis_points", "spread": unit_setting}[name]
            end = m.end(name)
            following = text[end : end + 3]
            if following.lstrip().startswith("%"):
                if unit == "basis_points":
                    diags.append("percent_sign_after_bps_capture:treated_as_percent")
                unit = "percent"
            break
    if raw_num is None:
        return None, None, None
    try:
        num = float(raw_num)
    except ValueError:
        diags.append(f"unparsed_spread:{raw_num}")
        return None, None, raw_num
    if unit == "percent":
        return round(num * 100.0, 6), percent_to_decimal(num), raw_num
    if unit == "basis_points":
        return num, bps_to_decimal(num), raw_num
    diags.append("spread_unit_unspecified")
    return None, None, raw_num


def parse_rate_text(text: str | None, parser: RateParser | None, norm: NormalizationSpec | None = None) -> RateResult:
    """Parse ``S+450, 0.50% Floor`` style text using template patterns (index aliases are template-specific)."""
    res = RateResult(raw=text or "")
    if not text:
        return res
    t = collapse_ws(text)
    pattern = parser.pattern if parser else GENERIC_RATE_PATTERN
    aliases = dict(parser.index_aliases) if parser else {}
    if norm:
        for k, v in norm.reference_index_aliases.items():
            aliases.setdefault(k, v)
    unit_setting = parser.spread_unit if parser else "auto"
    if unit_setting == "auto" and norm and norm.spread_input_unit != "auto":
        unit_setting = norm.spread_input_unit
    m = re.search(pattern, t)
    if m:
        res.matched = True
        gd = m.groupdict()
        idx, note = resolve_index(gd.get("index"), aliases)
        res.reference_index = idx
        if note and note.startswith("unresolved"):
            res.diagnostics.append(note)
        bps, dec, raw = _spread_from_match(m, t, "basis_points" if unit_setting == "auto" else unit_setting, res.diagnostics)
        res.spread_bps, res.spread, res.spread_raw = bps, dec, raw
    floor_pat = parser.floor_pattern if parser and parser.floor_pattern else GENERIC_FLOOR_PATTERN
    fm = re.search(floor_pat, t)
    if fm:
        gd = fm.groupdict()
        try:
            if gd.get("floor_pct") is not None:
                res.rate_floor = percent_to_decimal(float(gd["floor_pct"]))
            elif gd.get("floor_bps") is not None:
                res.rate_floor = bps_to_decimal(float(gd["floor_bps"]))
        except ValueError:
            res.diagnostics.append("unparsed_floor")
    pik_pat = parser.pik_pattern if parser and parser.pik_pattern else GENERIC_PIK_PATTERN
    pm = re.search(pik_pat, t)
    if pm:
        gd = pm.groupdict()
        try:
            if gd.get("pik_pct") is not None:
                res.pik_rate = percent_to_decimal(float(gd["pik_pct"]))
            elif gd.get("pik_bps") is not None:
                res.pik_rate = bps_to_decimal(float(gd["pik_bps"]))
        except ValueError:
            res.diagnostics.append("unparsed_pik")
    cash_pat = parser.cash_pattern if parser and parser.cash_pattern else GENERIC_CASH_PATTERN
    cm = re.search(cash_pat, t)
    if cm:
        gd = cm.groupdict()
        try:
            if gd.get("cash_pct") is not None:
                res.cash_rate = percent_to_decimal(float(gd["cash_pct"]))
            elif gd.get("cash_bps") is not None:
                res.cash_rate = bps_to_decimal(float(gd["cash_bps"]))
        except ValueError:
            res.diagnostics.append("unparsed_cash")
    if parser and parser.interest_rate_pattern:
        im = re.search(parser.interest_rate_pattern, t)
        if im:
            gd = im.groupdict()
            try:
                if gd.get("rate_pct") is not None:
                    res.interest_rate = percent_to_decimal(float(gd["rate_pct"]))
                elif gd.get("rate_bps") is not None:
                    res.interest_rate = bps_to_decimal(float(gd["rate_bps"]))
            except ValueError:
                res.diagnostics.append("unparsed_interest_rate")
    if not m:
        fixed = re.fullmatch(r"(?P<pct>\d+(?:\.\d+)?)\s*%(?:\s*(?:Fixed|fixed|Cash|cash))?", t)
        cash_pik = re.search(r"(?P<cash>\d+(?:\.\d+)?)\s*%\s*(?:Cash|cash)\s*(?:plus|\+|/|and)\s*(?P<pik>\d+(?:\.\d+)?)\s*%\s*PIK", t)
        pik_only = re.match(r"^(?P<pik>\d+(?:\.\d+)?)\s*%\s*PIK\b", t)
        if fixed:
            res.matched = True
            res.interest_rate = percent_to_decimal(float(fixed.group("pct")))
        elif cash_pik:
            res.matched = True
            res.cash_rate = percent_to_decimal(float(cash_pik.group("cash")))
            res.pik_rate = percent_to_decimal(float(cash_pik.group("pik")))
            res.interest_rate = round(res.cash_rate + res.pik_rate, 10)
        elif pik_only:
            res.matched = True
            res.pik_rate = percent_to_decimal(float(pik_only.group("pik")))
            res.interest_rate = res.pik_rate
    return res


def split_industry_prefix(header: str, known_industries: list[str], position: str = "prefix") -> tuple[str | None, str]:
    """Split a configured industry from the issuer text only on exact configured match (13.4)."""
    h = collapse_ws(header)
    words = h.split(" ")
    if position == "infix":
        hk = text_key(h)
        for industry in sorted(known_industries, key=len, reverse=True):
            ik = text_key(industry)
            n = len(industry.split(" "))
            for start in range(0, len(words) - n + 1):
                if text_key(" ".join(words[start : start + n])) == ik and start + n < len(words):
                    return " ".join(words[start : start + n]), " ".join(words[start + n :]).strip()
        return None, h
    for industry in sorted(known_industries, key=len, reverse=True):
        if position == "prefix" and h.startswith(industry + " "):
            return industry, h[len(industry) :].strip()
        if position == "suffix" and h.endswith(" " + industry):
            return industry, h[: -len(industry)].strip()
    # Punctuation-insensitive exact match on a leading/trailing word span ("Paper & Forest" == "Paper And Forest").
    for industry in sorted(known_industries, key=len, reverse=True):
        n = len(industry.split(" "))
        if position == "prefix" and len(words) > n and text_key(" ".join(words[:n])) == text_key(industry):
            return " ".join(words[:n]), " ".join(words[n:]).strip()
        if position == "suffix" and len(words) > n and text_key(" ".join(words[-n:])) == text_key(industry):
            return " ".join(words[-n:]), " ".join(words[:-n]).strip()
    return None, h


def apply_composite_rule(rule: CompositeField, text: str | None, norm: NormalizationSpec | None = None, independent_industry: str | None = None) -> CompositeResult:
    """Apply one composite rule; returns normalized captures with transformations (13.2)."""
    result = CompositeResult(False, rule.id)
    if not text:
        return result
    t = collapse_ws(text)
    if rule.kind == "delimited":
        parts = [collapse_ws(p) for p in t.split(rule.delimiter or "|")]
        needed = max(rule.positions.values()) + 1 if rule.positions else 0
        if len(parts) < (rule.min_parts or needed):
            result.diagnostics.append(f"composite_delimited_parts:{len(parts)}<{rule.min_parts or needed}")
            return result
        gd = {name: (parts[idx] if idx < len(parts) and parts[idx] else None) for name, idx in rule.positions.items()}
        gd.pop("ignore", None)
        result.matched = True
    else:
        m = re.search(rule.pattern, t)
        if not m:
            result.diagnostics.append("composite_pattern_no_match")
            return result
        result.matched = True
        gd = m.groupdict()
    date_formats = norm.date_formats if norm else None
    legal = norm.legal_suffixes if norm else None

    # Header: optional industry prefix + issuer remainder.
    header = gd.get("header")
    if header is not None:
        industry: str | None = None
        remainder = header
        if rule.header_parser:
            industry, remainder = split_industry_prefix(header, rule.header_parser.known_industries, rule.header_parser.industry_position)
            if industry is None and independent_industry:
                cand, rem2 = split_industry_prefix(header, [independent_industry], rule.header_parser.industry_position)
                if cand:
                    industry, remainder = cand, rem2
            target = rule.header_parser.remainder_target
            if rule.header_parser.remainder_pattern:
                rm = re.search(rule.header_parser.remainder_pattern, collapse_ws(remainder))
                if rm and rm.groupdict().get("issuer"):
                    remainder = rm.group("issuer")
                    result.diagnostics.append("header:remainder_pattern_applied")
        else:
            target = "issuer"
        if industry:
            result.fields["industry"] = ParsedField("industry", industry, header, "industry_prefix_split")
        if target == "issuer":
            result.fields["issuer"] = ParsedField("issuer", normalize_issuer(remainder, legal), header, "issuer_normalized")
        else:
            result.fields[target] = ParsedField(target, collapse_ws(remainder), header, "header_remainder")

    for group, raw in gd.items():
        if raw is None or group in {"header", "rate"}:
            continue
        target = rule.capture_targets.get(group)
        if target is None:
            target = {"maturity": "maturity_date", "description": "description", "issuer": "issuer", "industry": "industry"}.get(group, group)
        if target == "maturity_date" or target == "issue_date":
            d, diag = parse_date(raw, date_formats)
            if diag:
                result.diagnostics.append(f"{target}:{diag}")
            result.fields[target] = ParsedField(target, d, raw, "date_normalized")
        elif target == "issuer":
            result.fields[target] = ParsedField(target, normalize_issuer(raw, legal), raw, "issuer_normalized")
        elif target == "description":
            result.fields[target] = ParsedField(target, normalize_description(raw), raw, "description_normalized")
        elif target in {"industry", "sector", "country", "investment_type", "footnote_markers"}:
            result.fields[target] = ParsedField(target, collapse_ws(raw), raw, "text")
        elif target == "reference_index":
            idx, note = resolve_index(raw, dict(rule.rate_parser.index_aliases) if rule.rate_parser else (dict(norm.reference_index_aliases) if norm else {}))
            if idx is None and note:
                result.diagnostics.append(note)
            result.fields[target] = ParsedField(target, idx, raw, "index_alias")
        elif target in {"spread", "spread_bps", "rate_floor", "pik_rate", "cash_rate", "interest_rate"}:
            from bdc_soi.normalization import coerce_value as _cv

            val, diag = _cv(target, raw, date_formats)
            if diag:
                result.diagnostics.append(f"{target}:{diag}")
            if target == "spread" and isinstance(val, (int, float)):
                result.fields["spread_bps"] = ParsedField("spread_bps", round(val * 10000.0, 6), raw, "decimal_to_bps")
            result.fields[target] = ParsedField(target, val, raw, "percent_to_decimal" if "%" in raw else "numeric")
        else:
            result.fields[target] = ParsedField(target, collapse_ws(raw), raw, "text")

    rate_text = gd.get("rate")
    if rate_text is not None:
        rr = parse_rate_text(rate_text, rule.rate_parser, norm)
        result.diagnostics.extend(f"rate:{d}" for d in rr.diagnostics)
        if rr.matched:
            if rr.reference_index is not None:
                result.fields["reference_index"] = ParsedField("reference_index", rr.reference_index, rate_text, "index_alias")
            if rr.spread_bps is not None:
                result.fields["spread_bps"] = ParsedField("spread_bps", rr.spread_bps, rr.spread_raw or rate_text, "spread_to_bps")
                result.fields["spread"] = ParsedField("spread", rr.spread, rr.spread_raw or rate_text, "spread_to_decimal")
            if rr.interest_rate is not None:
                result.fields["interest_rate"] = ParsedField("interest_rate", rr.interest_rate, rate_text, "percent_to_decimal")
        else:
            result.diagnostics.append("rate:unknown_rate_format")
        if rr.rate_floor is not None:
            result.fields["rate_floor"] = ParsedField("rate_floor", rr.rate_floor, rate_text, "floor_percent_to_decimal")
        if rr.pik_rate is not None:
            result.fields["pik_rate"] = ParsedField("pik_rate", rr.pik_rate, rate_text, "pik_percent_to_decimal")
        if rr.cash_rate is not None:
            result.fields["cash_rate"] = ParsedField("cash_rate", rr.cash_rate, rate_text, "cash_percent_to_decimal")
    return result


def as_output_dict(result: CompositeResult) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in result.fields.items():
        out[k] = v.value.isoformat() if isinstance(v.value, date) else v.value
    return out
