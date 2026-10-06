"""Canonical output model, fact inventory, and diagnostics records (SPEC 9, 11.1, 18)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Canonical field vocabulary
# ---------------------------------------------------------------------------

IDENTITY_FIELDS: tuple[str, ...] = (
    "holding_id",
    "cik",
    "company_name",
    "accession_number",
    "filing_date",
    "report_date",
    "form",
    "template_id",
    "engine_version",
)

TEXT_FIELDS: tuple[str, ...] = (
    "issuer",
    "issuer_name_raw",
    "description",
    "description_raw",
    "industry",
    "sector",
    "country",
    "investment_type",
    "reference_index",
    "currency",
    "affiliate_status",
    "controlled_status",
    "footnote_markers",
)

RATE_FIELDS: tuple[str, ...] = ("spread", "spread_bps", "cash_rate", "pik_rate", "rate_floor", "interest_rate")
DATE_FIELDS: tuple[str, ...] = ("issue_date", "maturity_date")
MONETARY_FIELDS: tuple[str, ...] = ("principal_amount", "face_amount", "cost", "amortized_cost", "fair_value")
COUNT_FIELDS: tuple[str, ...] = ("shares",)
PROPORTION_FIELDS: tuple[str, ...] = ("percent_of_net_assets",)
BOOLEAN_FIELDS: tuple[str, ...] = ("non_accrual_flag",)

NORMALIZED_FIELDS: tuple[str, ...] = (
    "issuer",
    "issuer_name_raw",
    "description",
    "description_raw",
    "industry",
    "sector",
    "country",
    "investment_type",
    "reference_index",
    "spread",
    "spread_bps",
    "cash_rate",
    "pik_rate",
    "rate_floor",
    "interest_rate",
    "issue_date",
    "maturity_date",
    "principal_amount",
    "face_amount",
    "shares",
    "cost",
    "amortized_cost",
    "fair_value",
    "percent_of_net_assets",
    "currency",
    "affiliate_status",
    "controlled_status",
    "non_accrual_flag",
    "footnote_markers",
)

LINEAGE_FIELDS: tuple[str, ...] = (
    "source_method",
    "source_document",
    "source_table",
    "source_context_ids",
    "source_fact_ids",
    "source_concepts",
    "dimension_signature",
    "member_labels",
    "field_lineage",
    "field_conflicts",
    "template_rule_ids",
    "extraction_confidence",
    "confidence_factors",
    "review_flags",
    "html_row_id",
    "holding_member_key",
    "reporting_currency",
    "fair_value_unit_original",
    "reconciliation_scope",
    "scope_rule",
    "scope_evidence",
    "identity_resolution",
    "match_group_id",
    "conflict_classes",
)

# Fields that templates may reference (mappable canonical fields). ``issuer_name``
# and ``security_description`` are accepted aliases (SPEC conversion note).
FIELD_ALIASES: dict[str, str] = {
    "issuer_name": "issuer",
    "security_description": "description",
    "raw_issuer_name": "issuer_name_raw",
    "raw_security_description": "description_raw",
    "raw_description": "description_raw",
}

MAPPABLE_FIELDS: frozenset[str] = frozenset(NORMALIZED_FIELDS) | frozenset(
    {"interest_rate_text", "total_fair_value", "total_cost", "total_amortized_cost", "percent_of_total"}
)

NUMERIC_FIELDS: frozenset[str] = frozenset(RATE_FIELDS + MONETARY_FIELDS + COUNT_FIELDS + PROPORTION_FIELDS)


def canonical_field(name: str) -> str:
    """Resolve template aliases to canonical field names."""
    return FIELD_ALIASES.get(name, name)


# ---------------------------------------------------------------------------
# Lineage
# ---------------------------------------------------------------------------


class LineageEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str  # xbrl_fact, xbrl_dimension_member, html_cell, parsed_composite_text, template_rule, reviewed_override, carry_forward
    raw_value: Any = None
    rule_id: str | None = None
    normalized_value: Any = None
    source_ref: str | None = None  # fact id, context id, cell address, override id
    transformation: str | None = None


class FieldConflict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    selected: Any
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    reason: str = ""
    conflict_class: str | None = None  # formatting | identity | semantic | numeric (classify_conflict)


class ConfidenceFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factor: str
    adjustment: float
    note: str | None = None


# ---------------------------------------------------------------------------
# Holding
# ---------------------------------------------------------------------------


class Holding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 9.1 identity
    holding_id: str = ""
    cik: str
    company_name: str | None = None
    accession_number: str
    filing_date: date | None = None
    report_date: date | None = None
    form: str | None = None
    template_id: str | None = None
    engine_version: str = ""

    # 9.2 normalized fields
    issuer: str | None = None
    issuer_name_raw: str | None = None
    description: str | None = None
    description_raw: str | None = None
    industry: str | None = None
    sector: str | None = None
    country: str | None = None
    investment_type: str | None = None
    reference_index: str | None = None
    spread: float | None = None
    spread_bps: float | None = None
    cash_rate: float | None = None
    pik_rate: float | None = None
    rate_floor: float | None = None
    interest_rate: float | str | None = None
    issue_date: date | None = None
    maturity_date: date | None = None
    principal_amount: float | None = None
    face_amount: float | None = None
    shares: float | None = None
    cost: float | None = None
    amortized_cost: float | None = None
    fair_value: float | None = None
    percent_of_net_assets: float | None = None
    currency: str | None = None
    affiliate_status: str | None = None
    controlled_status: str | None = None
    non_accrual_flag: bool | None = None
    footnote_markers: str | None = None

    # 9.3 lineage and diagnostics
    source_method: str = "unknown"
    source_document: str | None = None
    source_table: str | None = None
    source_context_ids: list[str] = Field(default_factory=list)
    source_fact_ids: list[str] = Field(default_factory=list)
    source_concepts: dict[str, str] = Field(default_factory=dict)
    dimension_signature: str | None = None
    member_labels: dict[str, str] = Field(default_factory=dict)
    field_lineage: dict[str, LineageEntry] = Field(default_factory=dict)
    field_conflicts: list[FieldConflict] = Field(default_factory=list)
    template_rule_ids: list[str] = Field(default_factory=list)
    extraction_confidence: float = 0.0
    confidence_factors: list[ConfidenceFactor] = Field(default_factory=list)
    review_flags: list[str] = Field(default_factory=list)
    html_row_id: str | None = None
    holding_member_key: str | None = None
    reporting_currency: str | None = None  # selected reporting currency of the fair value (D33)
    fair_value_unit_original: str | None = None  # unit tagged on the XBRL fair-value fact before any D33 decision
    # Reconciliation scope (D43): schedule | cash_equivalent_after_total | after_total_section | subsidiary_context
    reconciliation_scope: str = "schedule"
    scope_rule: str | None = None
    scope_evidence: str | None = None
    # Identity resolution (D44): row (unique evidence) | group (group-equivalent rows paired without row-level identity)
    identity_resolution: str = "row"
    match_group_id: str | None = None
    conflict_classes: dict[str, int] = Field(default_factory=dict)

    def set_field(
        self,
        field: str,
        value: Any,
        *,
        source: str,
        raw_value: Any = None,
        rule_id: str | None = None,
        source_ref: str | None = None,
        transformation: str | None = None,
    ) -> None:
        """Set a normalized field and record its lineage."""
        setattr(self, field, value)
        self.field_lineage[field] = LineageEntry(
            source=source,
            raw_value=raw_value,
            rule_id=rule_id,
            normalized_value=value,
            source_ref=source_ref,
            transformation=transformation,
        )
        if rule_id and rule_id not in self.template_rule_ids:
            self.template_rule_ids.append(rule_id)

    def add_flag(self, flag: str) -> None:
        if flag not in self.review_flags:
            self.review_flags.append(flag)

    def to_row(self) -> dict[str, Any]:
        """Flat row for tabular export; nested structures are JSON-encoded."""
        row: dict[str, Any] = {}
        for name in IDENTITY_FIELDS + NORMALIZED_FIELDS:
            val = getattr(self, name)
            row[name] = val.isoformat() if isinstance(val, date) else val
        row["source_method"] = self.source_method
        row["source_document"] = self.source_document
        row["source_table"] = self.source_table
        row["source_context_ids"] = json.dumps(self.source_context_ids)
        row["source_fact_ids"] = json.dumps(self.source_fact_ids)
        row["source_concepts"] = json.dumps(self.source_concepts, sort_keys=True)
        row["dimension_signature"] = self.dimension_signature
        row["member_labels"] = json.dumps(self.member_labels, sort_keys=True)
        row["field_lineage"] = json.dumps(
            {k: v.model_dump(mode="json") for k, v in sorted(self.field_lineage.items())}, sort_keys=True, default=str
        )
        row["field_conflicts"] = json.dumps([c.model_dump(mode="json") for c in self.field_conflicts], default=str)
        row["template_rule_ids"] = json.dumps(self.template_rule_ids)
        row["extraction_confidence"] = round(self.extraction_confidence, 4)
        row["confidence_factors"] = json.dumps([c.model_dump(mode="json") for c in self.confidence_factors])
        row["review_flags"] = json.dumps(self.review_flags)
        row["html_row_id"] = self.html_row_id
        row["holding_member_key"] = self.holding_member_key
        row["reporting_currency"] = self.reporting_currency
        row["fair_value_unit_original"] = self.fair_value_unit_original
        row["reconciliation_scope"] = self.reconciliation_scope
        row["scope_rule"] = self.scope_rule
        row["scope_evidence"] = self.scope_evidence
        row["identity_resolution"] = self.identity_resolution
        row["match_group_id"] = self.match_group_id
        row["conflict_classes"] = json.dumps(self.conflict_classes, sort_keys=True)
        return row


HOLDING_COLUMNS: tuple[str, ...] = IDENTITY_FIELDS + NORMALIZED_FIELDS + LINEAGE_FIELDS


# ---------------------------------------------------------------------------
# XBRL fact inventory (11.1)
# ---------------------------------------------------------------------------


class FactRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str
    concept_clark: str
    concept_prefixed: str
    local_name: str
    namespace: str
    standard_label: str | None = None
    documentation_label: str | None = None
    raw_value: str | None = None
    normalized_value: Any = None
    numeric_value: float | None = None
    is_nil: bool = False
    unit: str | None = None
    decimals: str | None = None
    context_id: str
    period_type: str  # instant | duration | forever
    period_start: date | None = None
    period_end: date | None = None
    dimensions: dict[str, str] = Field(default_factory=dict)  # axis clark -> member clark or typed value
    dimension_labels: dict[str, str] = Field(default_factory=dict)  # axis clark -> member label
    dimension_signature: str = ""
    in_soi_role: bool = False
    soi_roles: list[str] = Field(default_factory=list)
    mapped_field: str | None = None
    mapping_rule: str | None = None
    data_type: str | None = None
    order_index: int = 0

    def to_row(self) -> dict[str, Any]:
        d = self.model_dump(mode="json")
        d["dimensions"] = json.dumps(self.dimensions, sort_keys=True)
        d["dimension_labels"] = json.dumps(self.dimension_labels, sort_keys=True)
        d["soi_roles"] = json.dumps(self.soi_roles)
        d["normalized_value"] = None if self.normalized_value is None else str(self.normalized_value)
        return d


# ---------------------------------------------------------------------------
# Filing records and diagnostics (10, 18)
# ---------------------------------------------------------------------------


class FilingRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cik: str
    company_name: str | None = None
    accession_number: str
    form: str
    filing_date: date | None = None
    report_date: date | None = None
    primary_document: str | None = None
    is_xbrl: bool | None = None
    is_inline_xbrl: bool | None = None
    eligible: bool = False
    selected: bool = False
    reason: str = ""
    source_file: str | None = None

    def to_row(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class PackageFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    url: str
    local_path: str
    size: int
    sha256: str
    content_type: str | None = None
    role: str | None = None  # primary, instance, schema, linkbase, html, summary, metadata, other
    from_cache: bool = False


class FilingDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cik: str
    accession_number: str
    company_name: str | None = None
    report_date: date | None = None
    template_id: str | None = None
    status: str = "ok"  # ok | partial | failed
    phase: str | None = None
    xbrl_status: str = "not_run"
    html_status: str = "not_run"
    holdings_count: int = 0
    xbrl_holdings: int = 0
    html_rows: int = 0
    matched_rows: int = 0
    unmatched_html_rows: int = 0
    conflicts: int = 0
    selected_axis: str | None = None
    instance_document: str | None = None
    instance_kind: str | None = None
    fair_value_reconciliation: str | None = None
    cost_reconciliation: str | None = None
    amortized_cost_reconciliation: str | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def to_row(self) -> dict[str, Any]:
        d = self.model_dump(mode="json")
        d["errors"] = json.dumps(self.errors, default=str)
        d["notes"] = json.dumps(self.notes)
        return d


class ErrorRecord(BaseModel):
    """Structured exception record (SPEC 23)."""

    model_config = ConfigDict(extra="forbid")

    cik: str | None
    accession_number: str | None
    phase: str
    exception_type: str
    message: str
    traceback: str | None = None


def as_jsonable(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {k: as_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_jsonable(v) for v in value]
    return value
