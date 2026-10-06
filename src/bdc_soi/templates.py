"""Effective-dated company templates: schema, validation, and selection (SPEC 8).

Semantic decisions (see docs/decisions.md):

* Concept references may be Clark ``{uri}Local`` (exact), ``prefix:Local`` (exact local
  name within a namespace family), or bare ``Local`` (controlled local-name fallback).
  The ``{issuer-namespace}`` placeholder from the illustrative template is rejected
  for production templates.
* ``total_if_regex`` and ``subtotal_if_regex`` are evaluated before ``skip_if_regex``;
  a row classified as a total is retained for reconciliation and excluded from
  holdings. Identical patterns in both lists are a validation error.
* ``issuer_name`` / ``security_description`` are accepted aliases of the canonical
  ``issuer`` / ``description`` fields. Override match key ``raw_issuer_name`` is an
  alias of ``issuer_name_raw``.
* ``spread_output_format`` controls Excel display only; storage is decimal + bps.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from bdc_soi.models import MAPPABLE_FIELDS, canonical_field

PLACEHOLDER_NAMESPACE = "{issuer-namespace}"
_CLARK_RE = re.compile(r"^\{(?P<ns>[^{}]+)\}(?P<local>[A-Za-z_][\w.\-]*)$")
_PREFIXED_RE = re.compile(r"^(?P<prefix>[A-Za-z_][\w.\-]*):(?P<local>[A-Za-z_][\w.\-]*)$")
_LOCAL_RE = re.compile(r"^(?P<local>[A-Za-z_][\w.\-]*)$")

GENERIC_CIK = "generic"


class TemplateValidationError(ValueError):
    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("Template validation failed:\n- " + "\n- ".join(issues))


# ---------------------------------------------------------------------------
# Concept references
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConceptRef:
    kind: Literal["clark", "prefixed", "local"]
    local: str
    namespace: str | None = None
    prefix: str | None = None
    raw: str = ""

    def matches(self, clark: str, namespace: str, local: str, families: dict[str, re.Pattern[str]]) -> bool:
        if self.local != local:
            return False
        if self.kind == "clark":
            return clark == f"{{{self.namespace}}}{self.local}"
        if self.kind == "prefixed":
            pat = families.get(self.prefix or "")
            return bool(pat and pat.search(namespace))
        return True


def parse_concept_ref(ref: str) -> ConceptRef:
    ref = ref.strip()
    if ref.startswith(PLACEHOLDER_NAMESPACE):
        raise ValueError(f"placeholder namespace reference is not allowed: {ref!r}")
    m = _CLARK_RE.match(ref)
    if m:
        return ConceptRef("clark", m.group("local"), namespace=m.group("ns"), raw=ref)
    m = _PREFIXED_RE.match(ref)
    if m:
        return ConceptRef("prefixed", m.group("local"), prefix=m.group("prefix"), raw=ref)
    m = _LOCAL_RE.match(ref)
    if m:
        return ConceptRef("local", m.group("local"), raw=ref)
    raise ValueError(f"malformed concept reference: {ref!r}")


def _compile_all(patterns: list[str], where: str, issues: list[str]) -> None:
    for pat in patterns:
        try:
            re.compile(pat)
        except re.error as exc:
            issues.append(f"{where}: regex does not compile {pat!r}: {exc}")


# ---------------------------------------------------------------------------
# Schema models
# ---------------------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RowAxesSpec(_Strict):
    explicit_qnames: list[str] = Field(default_factory=list)
    regex: list[str] = Field(default_factory=list)
    exclude_regex: list[str] = Field(default_factory=list)
    exclude_member_regex: list[str] = Field(default_factory=list)  # member labels that are not holdings (evidence required)
    exclude_member_evidence: str | None = None


class FieldPreferenceItem(_Strict):
    namespace: str
    concept: str


class ContextFilters(_Strict):
    require_report_date: bool = True
    allowed_period_types: list[Literal["instant", "duration"]] = Field(default_factory=lambda: ["instant"])
    excluded_axes_regex: list[str] = Field(default_factory=list)


class XbrlSpec(_Strict):
    role_regex: list[str] = Field(default_factory=list)
    row_axes: RowAxesSpec = Field(default_factory=RowAxesSpec)
    field_concepts: dict[str, list[str]] = Field(default_factory=dict)
    field_regex: dict[str, list[str]] = Field(default_factory=dict)
    field_preference: dict[str, list[FieldPreferenceItem]] = Field(default_factory=dict)
    context_filters: ContextFilters = Field(default_factory=ContextFilters)
    total_concepts: dict[str, list[str]] = Field(default_factory=dict)
    dimension_fields: dict[str, str] = Field(default_factory=dict)  # axis ref -> canonical field

    @field_validator("field_concepts", "field_regex", "total_concepts", mode="before")
    @classmethod
    def _canon_keys(cls, v: dict[str, Any]) -> dict[str, Any]:
        return {canonical_field(k): val for k, val in (v or {}).items()}

    @field_validator("field_preference", mode="before")
    @classmethod
    def _canon_pref_keys(cls, v: dict[str, Any]) -> dict[str, Any]:
        return {canonical_field(k): val for k, val in (v or {}).items()}

    @field_validator("dimension_fields", mode="before")
    @classmethod
    def _canon_dim_values(cls, v: dict[str, Any]) -> dict[str, Any]:
        return {k: canonical_field(val) for k, val in (v or {}).items()}


class RateParser(_Strict):
    pattern: str
    floor_pattern: str | None = None
    pik_pattern: str | None = None
    cash_pattern: str | None = None
    interest_rate_pattern: str | None = None  # named group rate_pct (percent) or rate_bps
    index_aliases: dict[str, str] = Field(default_factory=dict)
    spread_unit: Literal["basis_points", "percent", "auto"] = "auto"


class TableDetection(_Strict):
    heading_regex: list[str] = Field(default_factory=list)
    required_terms: list[str] = Field(default_factory=list)
    optional_terms: list[str] = Field(default_factory=list)
    excluded_terms: list[str] = Field(default_factory=list)
    minimum_score: float = 6
    max_heading_distance: int = 20


class HeaderRows(_Strict):
    min: int = 1
    max: int = 4


class ScaleSpec(_Strict):
    source: Literal["fixed", "table_then_document", "table_only", "document_only"] = "table_then_document"
    fixed_multiplier: int | None = None
    thousands_regex: list[str] = Field(default_factory=list)
    millions_regex: list[str] = Field(default_factory=list)
    default: int = 1


class GroupHeadingRule(_Strict):
    regex: str
    target: str

    @field_validator("target", mode="before")
    @classmethod
    def _canon(cls, v: str) -> str:
        return canonical_field(v)


class RowRules(_Strict):
    carry_forward: list[str] = Field(default_factory=list)
    group_heading_rules: list[GroupHeadingRule] = Field(default_factory=list)
    known_industries: list[str] = Field(default_factory=list)  # heading vocabulary disclosed by the filing (evidence in template)
    carry_forward_across_tables: bool = False
    blanks_meaningful: list[str] = Field(default_factory=list)
    group_heading_target: str | None = None
    skip_if_regex: list[str] = Field(default_factory=list)
    total_if_regex: list[str] = Field(default_factory=list)
    subtotal_if_regex: list[str] = Field(default_factory=list)
    footnote_if_regex: list[str] = Field(default_factory=list)
    require_any_numeric: list[str] = Field(default_factory=list)

    @field_validator("carry_forward", "blanks_meaningful", "require_any_numeric", mode="before")
    @classmethod
    def _canon_list(cls, v: list[str]) -> list[str]:
        return [canonical_field(x) for x in (v or [])]

    @field_validator("group_heading_target", mode="before")
    @classmethod
    def _canon_target(cls, v: str | None) -> str | None:
        return canonical_field(v) if v else v


class PeriodSelection(_Strict):
    prefer_report_date: bool = True
    allow_undated_tables: bool = True


class HtmlSpec(_Strict):
    table_detection: TableDetection = Field(default_factory=TableDetection)
    header_rows: HeaderRows = Field(default_factory=HeaderRows)
    header_aliases: dict[str, list[str]] = Field(default_factory=dict)
    scale: ScaleSpec = Field(default_factory=ScaleSpec)
    row_rules: RowRules = Field(default_factory=RowRules)
    period_selection: PeriodSelection = Field(default_factory=PeriodSelection)
    rate_parser: RateParser | None = None
    prefer_html_fields: list[str] = Field(default_factory=list)  # HTML cell supersedes composite/dimension-derived text (never direct facts)
    disabled: bool = False  # HTML extraction unsupported for this layout; XBRL results are retained (visible blocker)
    disabled_reason: str | None = None

    @field_validator("prefer_html_fields", mode="before")
    @classmethod
    def _canon_prefer(cls, v: list[str]) -> list[str]:
        return [canonical_field(x) for x in (v or [])]

    @field_validator("header_aliases", mode="before")
    @classmethod
    def _canon_keys(cls, v: dict[str, Any]) -> dict[str, Any]:
        return {canonical_field(k): val for k, val in (v or {}).items()}


class HeaderParser(_Strict):
    known_industries: list[str] = Field(default_factory=list)
    industry_position: Literal["prefix", "suffix", "infix"] = "prefix"  # infix: known industry anywhere; text after it is the issuer
    remainder_target: str = "issuer"
    remainder_pattern: str | None = None  # optional regex with an ``issuer`` group applied to the remainder

    @field_validator("remainder_target", mode="before")
    @classmethod
    def _canon(cls, v: str) -> str:
        return canonical_field(v)


class CompositeField(_Strict):
    id: str
    source_field: str
    pattern: str = ""  # regex with named groups; empty when kind == "delimited"
    kind: Literal["regex", "delimited"] = "regex"
    delimiter: str | None = None  # kind == "delimited": split character(s)
    positions: dict[str, int] = Field(default_factory=dict)  # kind == "delimited": canonical field or group name -> 0-based part index
    min_parts: int | None = None
    applies_to: Literal["xbrl", "html", "both"] = "both"
    precedence: Literal["direct_first", "composite_first"] = "direct_first"
    header_parser: HeaderParser | None = None
    rate_parser: RateParser | None = None
    capture_targets: dict[str, str] = Field(default_factory=dict)  # named group -> canonical field

    @field_validator("source_field", mode="before")
    @classmethod
    def _canon(cls, v: str) -> str:
        return canonical_field(v)

    @field_validator("capture_targets", mode="before")
    @classmethod
    def _canon_targets(cls, v: dict[str, str]) -> dict[str, str]:
        return {k: canonical_field(val) for k, val in (v or {}).items()}


class LegalSuffixes(_Strict):
    remove_preceding_comma: bool = True
    strip_trailing_period: bool = True


class NormalizationSpec(_Strict):
    legal_suffixes: LegalSuffixes = Field(default_factory=LegalSuffixes)
    date_formats: list[str] = Field(default_factory=lambda: ["%m/%d/%Y", "%Y-%m-%d"])
    spread_input_unit: Literal["basis_points", "percent", "auto"] = "auto"
    spread_output_format: Literal["percent", "decimal", "basis_points"] = "decimal"
    reference_index_aliases: dict[str, str] = Field(default_factory=dict)


class OverrideMatch(_Strict):
    report_date: date
    accession_number: str | None = None
    issuer_name_raw: str | None = None
    description_raw: str | None = None
    holding_member_key: str | None = None
    holding_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = dict(data)
            for alias, canon in (("raw_issuer_name", "issuer_name_raw"), ("raw_description", "description_raw"), ("raw_security_description", "description_raw"), ("accession", "accession_number")):
                if alias in data:
                    data[canon] = data.pop(alias)
        return data

    @model_validator(mode="after")
    def _needs_identity(self) -> "OverrideMatch":
        if not any([self.issuer_name_raw, self.description_raw, self.holding_member_key, self.holding_id]):
            raise ValueError("override match requires at least one of issuer_name_raw, description_raw, holding_member_key, holding_id")
        return self


class OverrideProvenance(_Strict):
    source_type: str
    source_reference: str
    reviewed_by: str
    reviewed_at: date
    rationale: str
    source_url: str | None = None


class Override(_Strict):
    id: str
    match: OverrideMatch
    set: dict[str, Any]
    provenance: OverrideProvenance

    @field_validator("set", mode="before")
    @classmethod
    def _canon_set(cls, v: dict[str, Any]) -> dict[str, Any]:
        return {canonical_field(k): val for k, val in (v or {}).items()}


class TemplateValidationRules(_Strict):
    allow_negative_fair_value: bool = False  # explicit allowance (SPEC 16.3) with evidence in the template
    allow_negative_fair_value_evidence: str | None = None
    # Optional evidence-backed override of the SPEC 16.1 source ranking, e.g. ["html_template_total", "xbrl_no_dimensions"]
    # when the undimensioned XBRL fact is a broader total (investments plus cash equivalents) than the SOI holdings.
    total_source_preference: list[str] = Field(default_factory=list)
    total_source_preference_evidence: str | None = None
    # D33 (revised): a fair-value fact tagged in a non-USD unit may be reported in the schedule currency only when the
    # template records documented reporting-currency evidence from the filing (accounting-policy note, schedule
    # footnote defining currency markers for the par column, USD total fact); a column `$` symbol alone is not enough.
    reporting_currency_evidence: list[str] = Field(default_factory=list)


class TemplateVersion(_Strict):
    id: str
    priority: int = 0
    effective_from: date
    effective_to: date | None = None
    forms: list[str] | None = None
    accessions: list[str] | None = None
    status: Literal["production", "draft", "placeholder"] = "production"
    description: str | None = None
    evidence: list[str] = Field(default_factory=list)
    xbrl: XbrlSpec = Field(default_factory=XbrlSpec)
    html: HtmlSpec = Field(default_factory=HtmlSpec)
    composite_fields: list[CompositeField] = Field(default_factory=list)
    normalization: NormalizationSpec = Field(default_factory=NormalizationSpec)
    validation: TemplateValidationRules = Field(default_factory=TemplateValidationRules)
    overrides: list[Override] = Field(default_factory=list)

    def covers(self, d: date) -> bool:
        if d < self.effective_from:
            return False
        return self.effective_to is None or d <= self.effective_to

    def range_width_days(self) -> float:
        if self.effective_to is None:
            return float("inf")
        return float((self.effective_to - self.effective_from).days)


class TemplateFile(_Strict):
    schema_version: int = 1
    cik: str
    company_name: str | None = None
    namespace_families: dict[str, str] = Field(default_factory=dict)
    templates: list[TemplateVersion] = Field(default_factory=list)

    @field_validator("cik", mode="before")
    @classmethod
    def _cik_str(cls, v: Any) -> str:
        s = str(v).strip()
        return s if s == GENERIC_CIK else s.lstrip("0") or "0"


# ---------------------------------------------------------------------------
# Semantic validation (8.4)
# ---------------------------------------------------------------------------


def _check_field_names(mapping: dict[str, Any], where: str, issues: list[str]) -> None:
    for name in mapping:
        if name not in MAPPABLE_FIELDS:
            issues.append(f"{where}: unknown canonical field {name!r}")


def _check_fields(names: list[str] | None, where: str, issues: list[str]) -> None:
    for name in names or []:
        if name not in MAPPABLE_FIELDS:
            issues.append(f"{where}: unknown canonical field {name!r}")


def validate_template_version(tv: TemplateVersion, where: str, issues: list[str]) -> None:
    x = tv.xbrl
    _compile_all(x.role_regex, f"{where}.xbrl.role_regex", issues)
    _compile_all(x.row_axes.regex, f"{where}.xbrl.row_axes.regex", issues)
    _compile_all(x.row_axes.exclude_regex, f"{where}.xbrl.row_axes.exclude_regex", issues)
    _compile_all(x.row_axes.exclude_member_regex, f"{where}.xbrl.row_axes.exclude_member_regex", issues)
    if x.row_axes.exclude_member_regex and not x.row_axes.exclude_member_evidence:
        issues.append(f"{where}.xbrl.row_axes: exclude_member_regex requires exclude_member_evidence")
    _compile_all(x.context_filters.excluded_axes_regex, f"{where}.xbrl.context_filters.excluded_axes_regex", issues)
    _check_field_names(x.field_concepts, f"{where}.xbrl.field_concepts", issues)
    _check_field_names(x.field_regex, f"{where}.xbrl.field_regex", issues)
    _check_field_names(x.field_preference, f"{where}.xbrl.field_preference", issues)
    _check_field_names(x.total_concepts, f"{where}.xbrl.total_concepts", issues)
    _check_fields(list(x.dimension_fields.values()), f"{where}.xbrl.dimension_fields", issues)
    for fld, pats in x.field_regex.items():
        _compile_all(pats, f"{where}.xbrl.field_regex.{fld}", issues)
    for fld, refs in list(x.field_concepts.items()) + list(x.total_concepts.items()):
        for ref in refs:
            try:
                parse_concept_ref(ref)
            except ValueError as exc:
                if tv.status == "placeholder" and PLACEHOLDER_NAMESPACE in ref:
                    continue
                issues.append(f"{where}.xbrl.{fld}: {exc}")
    for q in x.row_axes.explicit_qnames:
        try:
            parse_concept_ref(q)
        except ValueError as exc:
            if tv.status == "placeholder" and PLACEHOLDER_NAMESPACE in q:
                continue
            issues.append(f"{where}.xbrl.row_axes.explicit_qnames: {exc}")
    for axis in x.dimension_fields:
        try:
            parse_concept_ref(axis)
        except ValueError as exc:
            issues.append(f"{where}.xbrl.dimension_fields: {exc}")

    h = tv.html
    td = h.table_detection
    _compile_all(td.heading_regex, f"{where}.html.table_detection.heading_regex", issues)
    _compile_all(td.required_terms + td.optional_terms + td.excluded_terms, f"{where}.html.table_detection.terms", issues)
    _check_field_names(h.header_aliases, f"{where}.html.header_aliases", issues)
    for fld, pats in h.header_aliases.items():
        _compile_all(pats, f"{where}.html.header_aliases.{fld}", issues)
    if h.header_rows.min < 1 or h.header_rows.max < h.header_rows.min:
        issues.append(f"{where}.html.header_rows: invalid range")
    sc = h.scale
    _compile_all(sc.thousands_regex + sc.millions_regex, f"{where}.html.scale", issues)
    if sc.source == "fixed" and sc.fixed_multiplier is None:
        issues.append(f"{where}.html.scale: source 'fixed' requires fixed_multiplier")
    if sc.source != "fixed" and sc.default not in (1, 1000, 1_000_000):
        issues.append(f"{where}.html.scale.default: must be 1, 1000 or 1000000")
    rr = h.row_rules
    _compile_all(rr.skip_if_regex + rr.total_if_regex + rr.subtotal_if_regex + rr.footnote_if_regex, f"{where}.html.row_rules", issues)
    _check_fields(rr.carry_forward, f"{where}.html.row_rules.carry_forward", issues)
    _check_fields(rr.blanks_meaningful, f"{where}.html.row_rules.blanks_meaningful", issues)
    _check_fields(rr.require_any_numeric, f"{where}.html.row_rules.require_any_numeric", issues)
    if rr.group_heading_target and rr.group_heading_target not in MAPPABLE_FIELDS:
        issues.append(f"{where}.html.row_rules.group_heading_target: unknown field {rr.group_heading_target!r}")
    # Row rule / total rule conflicts: identical patterns in skip and total lists, or a
    # carried-forward field declared as blank-meaningful, are contradictory.
    for pat in rr.total_if_regex + rr.subtotal_if_regex:
        if pat in rr.skip_if_regex:
            issues.append(f"{where}.html.row_rules: pattern {pat!r} appears in both skip_if_regex and total/subtotal_if_regex (row rule conflicts with total rule)")
    for ghr in rr.group_heading_rules:
        _compile_all([ghr.regex], f"{where}.html.row_rules.group_heading_rules", issues)
        if ghr.target not in MAPPABLE_FIELDS and ghr.target != "ignore":
            issues.append(f"{where}.html.row_rules.group_heading_rules: unknown target {ghr.target!r}")
    _check_fields(h.prefer_html_fields, f"{where}.html.prefer_html_fields", issues)
    if h.disabled and not h.disabled_reason:
        issues.append(f"{where}.html: disabled requires disabled_reason")
    if h.rate_parser:
        _compile_all([p for p in (h.rate_parser.pattern, h.rate_parser.floor_pattern, h.rate_parser.pik_pattern, h.rate_parser.cash_pattern) if p], f"{where}.html.rate_parser", issues)
    for fld in rr.carry_forward:
        if fld in rr.blanks_meaningful:
            issues.append(f"{where}.html.row_rules: field {fld!r} is both carried forward and blank-meaningful")

    seen_cf: set[str] = set()
    for cf in tv.composite_fields:
        cw = f"{where}.composite_fields[{cf.id}]"
        if cf.id in seen_cf:
            issues.append(f"{cw}: duplicate composite rule id")
        seen_cf.add(cf.id)
        if cf.source_field not in MAPPABLE_FIELDS:
            issues.append(f"{cw}: unknown source_field {cf.source_field!r}")
        if cf.kind == "delimited":
            if not cf.delimiter:
                issues.append(f"{cw}: delimited rule requires a delimiter")
            if not cf.positions:
                issues.append(f"{cw}: delimited rule requires positions")
            for name in cf.positions:
                target = cf.capture_targets.get(name, name)
                if target not in MAPPABLE_FIELDS and name not in {"header", "rate", "maturity", "description", "issuer", "industry", "ignore"}:
                    issues.append(f"{cw}: position {name!r} has no canonical target")
            compiled = None
        else:
            try:
                compiled = re.compile(cf.pattern)
            except re.error as exc:
                issues.append(f"{cw}: pattern does not compile: {exc}")
                compiled = None
        if compiled is not None:
            for group in compiled.groupindex:
                target = cf.capture_targets.get(group, group)
                if target not in MAPPABLE_FIELDS and group not in {"header", "rate", "maturity", "description", "issuer", "industry"}:
                    issues.append(f"{cw}: capture group {group!r} has no canonical target")
        for target in cf.capture_targets.values():
            if target not in MAPPABLE_FIELDS:
                issues.append(f"{cw}: unknown capture target {target!r}")
        if cf.header_parser and cf.header_parser.remainder_target not in MAPPABLE_FIELDS:
            issues.append(f"{cw}.header_parser: unknown remainder_target")
        if cf.header_parser and cf.header_parser.remainder_pattern:
            try:
                rp = re.compile(cf.header_parser.remainder_pattern)
                if "issuer" not in rp.groupindex:
                    issues.append(f"{cw}.header_parser.remainder_pattern: must define an 'issuer' named group")
            except re.error as exc:
                issues.append(f"{cw}.header_parser.remainder_pattern: regex does not compile: {exc}")
        if cf.rate_parser:
            _compile_all([p for p in (cf.rate_parser.pattern, cf.rate_parser.floor_pattern, cf.rate_parser.pik_pattern, cf.rate_parser.cash_pattern, cf.rate_parser.interest_rate_pattern) if p], f"{cw}.rate_parser", issues)
            try:
                rp = re.compile(cf.rate_parser.pattern)
                groups = set(rp.groupindex)
                if not ({"spread_bps", "spread_pct", "spread"} & groups):
                    issues.append(f"{cw}.rate_parser.pattern: must capture spread_bps, spread_pct or spread")
                if "spread" in groups and cf.rate_parser.spread_unit == "auto":
                    issues.append(f"{cw}.rate_parser: capture group 'spread' requires an explicit spread_unit (percentage/scale unit unspecified)")
            except re.error:
                pass

    for ev in tv.validation.reporting_currency_evidence:
        if not re.search(r"\d{10}-\d{2}-\d{6}", ev):
            issues.append(f"{where}.validation.reporting_currency_evidence: each entry must cite the accession number it was read from: {ev[:60]!r}")
    if tv.validation.allow_negative_fair_value and not tv.validation.allow_negative_fair_value_evidence:
        issues.append(f"{where}.validation: allow_negative_fair_value requires allow_negative_fair_value_evidence")
    if tv.validation.total_source_preference:
        if not tv.validation.total_source_preference_evidence:
            issues.append(f"{where}.validation: total_source_preference requires total_source_preference_evidence")
        allowed = {"xbrl_template_total", "xbrl_no_dimensions", "html_template_total", "html_generic_total", "xbrl_classification_subtotal", "html_subtotal"}
        for s in tv.validation.total_source_preference:
            if s not in allowed:
                issues.append(f"{where}.validation.total_source_preference: unknown source {s!r}")
    nz = tv.normalization
    for fmt in nz.date_formats:
        if "%" not in fmt:
            issues.append(f"{where}.normalization.date_formats: {fmt!r} is not a strptime format")

    seen_ov: set[str] = set()
    for ov in tv.overrides:
        ow = f"{where}.overrides[{ov.id}]"
        if ov.id in seen_ov:
            issues.append(f"{ow}: duplicate override id")
        seen_ov.add(ov.id)
        _check_field_names(ov.set, f"{ow}.set", issues)
        if not ov.set:
            issues.append(f"{ow}: set must not be empty")
        if not ov.match.accession_number and not ov.match.report_date:
            issues.append(f"{ow}: match must identify accession or report_date")
        if ov.provenance.reviewed_by.lower().endswith("@example.com"):
            issues.append(f"{ow}: reviewer is the example placeholder")


def _date_overlap(a: TemplateVersion, b: TemplateVersion) -> bool:
    a_end = a.effective_to or date.max
    b_end = b.effective_to or date.max
    return a.effective_from <= b_end and b.effective_from <= a_end


def _forms_overlap(a: TemplateVersion, b: TemplateVersion) -> bool:
    if a.forms is None or b.forms is None:
        return True
    return bool(set(a.forms) & set(b.forms))


def validate_template_file(tf: TemplateFile, where: str = "template") -> list[str]:
    issues: list[str] = []
    for prefix, pat in tf.namespace_families.items():
        try:
            re.compile(pat)
        except re.error as exc:
            issues.append(f"{where}.namespace_families.{prefix}: regex does not compile: {exc}")
    ids = [t.id for t in tf.templates]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        issues.append(f"{where}: duplicate template id {dup!r}")
    for tv in tf.templates:
        if tv.effective_to is not None and tv.effective_to < tv.effective_from:
            issues.append(f"{where}[{tv.id}]: effective_to precedes effective_from")
        validate_template_version(tv, f"{where}[{tv.id}]", issues)
    active = [t for t in tf.templates if t.status != "placeholder"]
    for i, a in enumerate(active):
        for b in active[i + 1 :]:
            if not (_date_overlap(a, b) and _forms_overlap(a, b)):
                continue
            if a.accessions or b.accessions:
                continue  # accession-specific templates win deterministically
            if a.range_width_days() != b.range_width_days():
                continue  # narrowest range wins
            if a.priority != b.priority:
                continue  # priority wins
            issues.append(
                f"{where}: templates {a.id!r} and {b.id!r} overlap ambiguously "
                f"(same effective-range width and priority; no accession restriction)"
            )
    return issues


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


@dataclass
class LoadedTemplate:
    path: Path
    file: TemplateFile
    sha256: str
    issues: list[str]


def load_template_file(path: Path) -> LoadedTemplate:
    raw = path.read_bytes()
    data = yaml.safe_load(raw.decode("utf-8")) or {}
    issues: list[str] = []
    try:
        tf = TemplateFile.model_validate(data)
    except Exception as exc:  # pydantic ValidationError -> collected issue
        return LoadedTemplate(path, TemplateFile(cik="invalid"), hashlib.sha256(raw).hexdigest(), [f"{path.name}: schema error: {exc}"])
    issues.extend(validate_template_file(tf, path.name))
    return LoadedTemplate(path, tf, hashlib.sha256(raw).hexdigest(), issues)


class TemplateRegistry:
    """All templates in a directory, validated up front (SPEC 23: fail before extraction)."""

    def __init__(self, loaded: list[LoadedTemplate]):
        self.loaded = sorted(loaded, key=lambda lt: lt.path.name)
        self.by_cik: dict[str, LoadedTemplate] = {}
        issues: list[str] = []
        for lt in self.loaded:
            issues.extend(lt.issues)
            if lt.file.cik in self.by_cik:
                issues.append(f"{lt.path.name}: duplicate CIK {lt.file.cik} also defined in {self.by_cik[lt.file.cik].path.name}")
            self.by_cik[lt.file.cik] = lt
        self.issues = issues

    @classmethod
    def from_directory(cls, directory: Path) -> "TemplateRegistry":
        files = sorted(p for p in Path(directory).glob("*.yml")) + sorted(p for p in Path(directory).glob("*.yaml"))
        return cls([load_template_file(p) for p in files])

    def raise_if_invalid(self) -> None:
        if self.issues:
            raise TemplateValidationError(self.issues)

    @property
    def generic(self) -> TemplateFile | None:
        lt = self.by_cik.get(GENERIC_CIK)
        return lt.file if lt else None

    def checksums(self) -> dict[str, str]:
        return {lt.path.name: lt.sha256 for lt in self.loaded}

    def namespace_families(self) -> dict[str, re.Pattern[str]]:
        fams: dict[str, re.Pattern[str]] = {}
        gen = self.generic
        if gen:
            for prefix, pat in gen.namespace_families.items():
                fams[prefix] = re.compile(pat)
        return fams

    def select(
        self,
        cik: str,
        report_date: date,
        form: str | None = None,
        accession: str | None = None,
    ) -> tuple[TemplateVersion | None, str]:
        """Select the company template per SPEC 8.1. Returns (template, reason)."""
        lt = self.by_cik.get(cik)
        if lt is None:
            return None, "no_company_template_file"
        candidates = [t for t in lt.file.templates if t.covers(report_date) and t.status != "placeholder"]
        if form is not None:
            candidates = [t for t in candidates if t.forms is None or form in t.forms]
        if not candidates:
            placeholders = [t for t in lt.file.templates if t.status == "placeholder" and t.covers(report_date)]
            if placeholders:
                return None, f"only_placeholder_templates:{','.join(t.id for t in placeholders)}"
            return None, "no_template_covers_report_date"
        if accession:
            specific = [t for t in candidates if t.accessions and accession in t.accessions]
            if len(specific) == 1:
                return specific[0], "accession_specific"
            if len(specific) > 1:
                raise TemplateValidationError([f"{cik}: multiple accession-specific templates match {accession}: {[t.id for t in specific]}"])
        candidates = [t for t in candidates if not t.accessions]
        if not candidates:
            return None, "only_accession_specific_templates_for_other_accessions"
        narrowest = min(t.range_width_days() for t in candidates)
        candidates = [t for t in candidates if t.range_width_days() == narrowest]
        if len(candidates) == 1:
            return candidates[0], "narrowest_effective_range"
        top = max(t.priority for t in candidates)
        candidates = [t for t in candidates if t.priority == top]
        if len(candidates) == 1:
            return candidates[0], "highest_priority"
        raise TemplateValidationError([f"{cik}: ambiguous template selection for {report_date}: {[t.id for t in candidates]}"])


def template_json_schema() -> dict[str, Any]:
    schema = TemplateFile.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "BDC SOI company template file"
    return schema


def write_json_schema(path: Path) -> None:
    path.write_text(json.dumps(template_json_schema(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_against_json_schema(path: Path, schema_path: Path) -> list[str]:
    import jsonschema

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data = _jsonable(data)
    validator = jsonschema.Draft202012Validator(schema)
    return [f"{path.name}: {e.json_path}: {e.message}" for e in sorted(validator.iter_errors(data), key=lambda e: str(e.path))]


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, date):
        return value.isoformat()
    return value
