"""Total reconciliation, validation rules and review queue (SPEC 16, 18.2)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from bdc_soi.config import ValidationConfig
from bdc_soi.models import Holding

TOTAL_FIELDS = ("fair_value", "cost", "amortized_cost")


@dataclass
class ReconciliationBridge:
    """Full-output reconciliation bridge: every exported holding is accounted for exactly once."""

    matched_sum: float = 0.0
    matched_count: int = 0
    xbrl_only_sum: float = 0.0
    xbrl_only_count: int = 0
    html_only_sum: float = 0.0
    html_only_count: int = 0
    after_total_sum: float = 0.0  # exported holdings listed after the schedule's grand-total row (section evidence)
    after_total_count: int = 0
    subsidiary_sum: float = 0.0  # exported holdings tagged with a subsidiary/legal-entity context
    subsidiary_count: int = 0
    complete_sum: float = 0.0  # all exported holdings carrying the field
    complete_count: int = 0
    in_scope_sum: float = 0.0  # complete minus the evidence-based section exclusions above
    complete_status: str | None = None  # complete exported sum vs the reported total (no scope exclusions)
    scope_rules: dict[str, int] = field(default_factory=dict)  # rows WITH this field populated, per reconciliation_scope
    scope_rows_all: dict[str, int] = field(default_factory=dict)  # every exported row per reconciliation_scope (incl. rows without the field)
    duplicate_candidate_sum: float = 0.0  # contradictory-identity duplicates (D46), outside the sums, kept in the output
    duplicate_candidate_count: int = 0
    acceptance: str = "not_assessed"  # not_assessed | blocked:<reason>
    matched_only_status: str | None = None  # diagnostic only; never the reconciliation status

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class ReconciliationResult:
    field: str
    status: str  # pass | fail | not_tested | no_holdings | ambiguous_total | review
    detail_sum: float | None
    reported_total: float | None
    difference: float | None
    tolerance: float | None
    selected_source: str | None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    holdings_counted: int = 0
    notes: list[str] = field(default_factory=list)
    bridge: ReconciliationBridge = field(default_factory=ReconciliationBridge)
    selected_location: str | None = None
    currency: str | None = None
    report_date: str | None = None

    def to_row(self, cik: str, accession: str) -> dict[str, Any]:
        return {
            "cik": cik,
            "accession_number": accession,
            "field": self.field,
            "status": self.status,
            "detail_sum": self.detail_sum,
            "reported_total": self.reported_total,
            "difference": self.difference,
            "tolerance": self.tolerance,
            "selected_source": self.selected_source,
            "holdings_counted": self.holdings_counted,
            "candidate_count": len(self.candidates),
            "candidates_top": json.dumps([c for c in self.candidates if c.get("rank", 9) <= 3][:20], default=str),
            "selected_location": self.selected_location,
            "currency": self.currency,
            "report_date": self.report_date,
            "matched_sum": self.bridge.matched_sum,
            "matched_count": self.bridge.matched_count,
            "xbrl_only_sum": self.bridge.xbrl_only_sum,
            "xbrl_only_count": self.bridge.xbrl_only_count,
            "html_only_sum": self.bridge.html_only_sum,
            "html_only_count": self.bridge.html_only_count,
            "after_total_sum": self.bridge.after_total_sum,
            "after_total_count": self.bridge.after_total_count,
            "subsidiary_sum": self.bridge.subsidiary_sum,
            "subsidiary_count": self.bridge.subsidiary_count,
            "complete_exported_sum": self.bridge.complete_sum,
            "complete_exported_count": self.bridge.complete_count,
            "in_scope_sum": self.bridge.in_scope_sum,
            "complete_status": self.bridge.complete_status,
            "scope_rules": json.dumps(self.bridge.scope_rules, sort_keys=True),
            "scope_rows_all": json.dumps(self.bridge.scope_rows_all, sort_keys=True),
            "duplicate_candidate_sum": self.bridge.duplicate_candidate_sum,
            "duplicate_candidate_count": self.bridge.duplicate_candidate_count,
            "acceptance": self.bridge.acceptance,
            "matched_only_status": self.bridge.matched_only_status,
            "notes": json.dumps(self.notes),
        }


def tolerance_for(reported: float, cfg: ValidationConfig) -> float:
    return max(cfg.total_absolute_tolerance, abs(reported) * cfg.total_relative_tolerance)


CASH_EQUIVALENT_RE = re.compile(r"money\s*market|liquidity\s+funds?|government\s+(?:obligations?\s+)?fund|treasury\s+(?:obligations?|bills?|portfolio|securities)|cash\s+equivalents?|\bother\s+cash\b|\bt-?bills?\b|\bcash\b", re.IGNORECASE)


def assign_reconciliation_scope(holdings: list[Holding], row_texts: dict[str, str] | None = None, section_headings: dict[str, str] | None = None) -> None:
    """Row-level reconciliation scope (D43). Every exported holding keeps a scope, a rule id and the source evidence:
    - ``schedule``: counted against the schedule total (default, incl. after-total continuation sections);
    - ``cash_equivalent_after_total``: listed after the schedule's grand-total row AND the row/section text names a
      cash-equivalent position (money market / liquidity / government or treasury fund, T-bill, 'Cash Equivalents',
      'Other Cash'); a legitimate position preserved in the output but outside the schedule total;
    - ``after_total_section``: after the grand total without cash-equivalent evidence (e.g. a consolidated
      subsidiary's own schedule, Audax 'Audax Credit BDC Equity, LLC'); stays in scope, flagged for review;
    - ``subsidiary_context``: XBRL facts tagged with a subsidiary/legal-entity context (not the consolidated total).
    Nothing is removed from the output; the scope only decides which sum a row contributes to."""
    row_texts = row_texts or {}
    section_headings = section_headings or {}
    for h in holdings:
        if h.reconciliation_scope == "contradictory_identity_duplicate":
            continue  # assigned from source evidence (D46) before scope assignment
        if any(f.startswith("xbrl_subsidiary_context") for f in h.review_flags):
            # A subsidiary/legal-entity dimension alone is not exclusion evidence (D47): the row stays in scope, flagged,
            # until a template records evidence that the consolidated total excludes the entity.
            h.reconciliation_scope, h.scope_rule = "schedule", "D47:subsidiary_dimension_in_scope_by_default"
            h.scope_evidence = "dimension " + next(f for f in h.review_flags if f.startswith("xbrl_subsidiary_context")) + "; no template evidence of exclusion from the consolidated total"
            continue
        if "html_row_after_total" not in h.review_flags:
            h.reconciliation_scope, h.scope_rule = "schedule", "D43:schedule_default"
            h.scope_evidence = "row of the schedule before the grand-total row (or an XBRL identifier-axis member in the schedule role); no after-total or duplicate evidence"
            continue
        rid = h.html_row_id or (h.source_table.split(":")[1] if h.source_table and ":" in h.source_table else "")
        text = " | ".join(t for t in (h.issuer or "", h.description or "", h.investment_type or "", row_texts.get(rid, ""), section_headings.get(rid, "")) if t)
        m = CASH_EQUIVALENT_RE.search(text)
        if m:
            h.reconciliation_scope, h.scope_rule = "cash_equivalent_after_total", "D43:cash_equivalent_after_total"
            h.scope_evidence = f"after grand-total row; cash-equivalent term '{m.group(0)}' in: {text[:160]}"
        else:
            h.reconciliation_scope, h.scope_rule = "after_total_section", "D43:after_total_section_in_scope"
            h.scope_evidence = f"after grand-total row without cash-equivalent evidence; kept in scope: {text[:160]}"
            h.add_flag("after_total_section_in_scope")


def reconcile_field(fld: str, holdings: list[Holding], candidates: list[dict[str, Any]], cfg: ValidationConfig, currency: str | None, source_preference: list[str] | None = None, report_date: str | None = None) -> ReconciliationResult:
    """Scoped reconciliation (SPEC 16, D43): ``status`` compares the sum of every exported holding whose
    ``reconciliation_scope`` is in scope (schedule, after_total_section) with the reported total; rows scoped
    ``cash_equivalent_after_total`` or ``subsidiary_context`` are reported separately in the bridge with their rule
    and evidence. ``complete_status`` compares the complete exported sum (no exclusions). Matched-only sums are
    diagnostics only. ``source_preference`` (template, evidence-backed) re-ranks candidate sources.
    """
    if source_preference:
        rerank = {src: i for i, src in enumerate(source_preference)}
        candidates = [({**c, "rank": rerank[c["source"]]} if c.get("source") in rerank else {**c, "rank": c.get("rank", 9) + len(rerank)}) for c in candidates]
    br = ReconciliationBridge()
    with_field = [h for h in holdings if getattr(h, fld) is not None]
    after_total = [h for h in with_field if h.reconciliation_scope == "cash_equivalent_after_total"]
    subsidiary = [h for h in with_field if h.reconciliation_scope == "subsidiary_context"]
    duplicates = [h for h in with_field if h.reconciliation_scope == "contradictory_identity_duplicate"]
    in_scope = [h for h in with_field if h.reconciliation_scope in {"schedule", "after_total_section"}]
    for h in with_field:
        br.scope_rules[h.reconciliation_scope] = br.scope_rules.get(h.reconciliation_scope, 0) + 1
    for h in holdings:
        br.scope_rows_all[h.reconciliation_scope] = br.scope_rows_all.get(h.reconciliation_scope, 0) + 1
    br.duplicate_candidate_sum, br.duplicate_candidate_count = round(sum(getattr(h, fld) for h in duplicates), 2), len(duplicates)
    blocked = [h for h in holdings if any(f.startswith("contradictory_identity_candidate") for f in h.review_flags)]
    if blocked:
        br.acceptance = f"blocked:unresolved_identity_contradiction:{len(blocked)}_candidates"
    br.complete_sum, br.complete_count = round(sum(getattr(h, fld) for h in with_field), 2), len(with_field)
    br.after_total_sum, br.after_total_count = round(sum(getattr(h, fld) for h in after_total), 2), len(after_total)
    br.subsidiary_sum, br.subsidiary_count = round(sum(getattr(h, fld) for h in subsidiary), 2), len(subsidiary)
    for h in in_scope:
        v = getattr(h, fld)
        if h.source_method == "hybrid_xbrl_html":
            br.matched_sum += v
            br.matched_count += 1
        elif h.source_method == "html_only":
            br.html_only_sum += v
            br.html_only_count += 1
        else:
            br.xbrl_only_sum += v
            br.xbrl_only_count += 1
    br.matched_sum, br.html_only_sum, br.xbrl_only_sum = round(br.matched_sum, 2), round(br.html_only_sum, 2), round(br.xbrl_only_sum, 2)
    counted = len(in_scope)
    detail = round(sum(getattr(h, fld) for h in in_scope), 2) if in_scope else None
    br.in_scope_sum = detail or 0.0
    cands = [c for c in candidates if c.get("field") == fld]
    compatible: list[dict[str, Any]] = []
    for c in cands:
        unit = c.get("unit")
        if unit and currency and unit != currency:
            c = {**c, "excluded": f"unit_mismatch:{unit}!={currency}"}
        compatible.append(c)
    usable = [c for c in compatible if not c.get("excluded")]
    base = dict(field=fld, candidates=compatible, holdings_counted=counted, bridge=br, currency=currency, report_date=report_date)
    notes: list[str] = []
    if after_total:
        notes.append(f"outside the schedule total: {len(after_total)} exported cash-equivalent positions listed after the grand-total row (sum={br.after_total_sum}); rule D43:cash_equivalent_after_total; rows kept in the output")
    if subsidiary:
        notes.append(f"outside the consolidated total: {len(subsidiary)} exported holdings tagged with a subsidiary/legal-entity context (sum={br.subsidiary_sum}); rule D27")
    if duplicates:
        notes.append(f"outside the sums: {len(duplicates)} contradictory-identity duplicate candidates (sum={br.duplicate_candidate_sum}); rule D46; kept in the output, acceptance blocked")
    if br.acceptance.startswith("blocked"):
        notes.append(f"ACCEPTANCE {br.acceptance}: numerical reconciliation does not resolve identity; a reviewer must decide the contradictory candidates")
    if br.scope_rules.get("after_total_section"):
        notes.append(f"in scope: {br.scope_rules['after_total_section']} rows after the grand-total row without cash-equivalent evidence (rule D43:after_total_section_in_scope)")
    if not holdings or counted == 0:
        return ReconciliationResult(status="no_holdings", detail_sum=detail, reported_total=None, difference=None, tolerance=None, selected_source=None, notes=notes + ["no holdings carry this field"], **base)
    if not usable:
        return ReconciliationResult(status="not_tested", detail_sum=detail, reported_total=None, difference=None, tolerance=None, selected_source=None, notes=notes + ["no reported total candidate"], **base)
    best_rank = min(c["rank"] for c in usable)
    top = [c for c in usable if c["rank"] == best_rank]
    distinct = sorted({round(float(c["value"]), 2) for c in top})
    if len(distinct) > 1:
        tol = tolerance_for(max(abs(v) for v in distinct), cfg)
        if max(distinct) - min(distinct) > tol:
            shown = distinct[:10] + (["..."] if len(distinct) > 10 else [])
            return ReconciliationResult(status="ambiguous_total", detail_sum=detail, reported_total=None, difference=None, tolerance=tol, selected_source=None, notes=notes + [f"{len(distinct)} equally ranked candidates disagree: {shown}"], **base)
    chosen = sorted(top, key=lambda c: (str(c.get("source")), str(c.get("fact_id") or c.get("row_id"))))[0]
    reported = float(chosen["value"])
    tol = tolerance_for(reported, cfg)
    diff = round(detail - reported, 2)
    status = "pass" if abs(diff) <= tol else "fail"
    br.complete_status = "pass" if abs(br.complete_sum - reported) <= tol else "fail"
    if br.complete_status != status:
        notes.append(f"scoped status {status} differs from complete-exported status {br.complete_status} (complete sum {br.complete_sum} vs reported {reported}); the exclusions above explain the difference")
    location = chosen.get("fact_id") and f"xbrl fact {chosen['fact_id']} ctx {chosen.get('context_id')} unit {chosen.get('unit')}" or f"html row {chosen.get('row_id')}: {str(chosen.get('row_text') or '')[:80]}"
    if br.matched_count:
        br.matched_only_status = "pass" if abs(br.matched_sum - reported) <= tol else "fail"
        if status == "fail":
            notes.append(f"diagnostic: matched-rows-only sum={br.matched_sum} would {'reconcile' if br.matched_only_status == 'pass' else 'not reconcile'}; xbrl-only={br.xbrl_only_sum} ({br.xbrl_only_count}), html-only={br.html_only_sum} ({br.html_only_count}); the status above is the scoped result")
    if status == "pass" and chosen.get("source") in {"xbrl_classification_subtotal", "html_subtotal"}:
        status = "review"
        notes.append("total selected from subtotal-level evidence")
    return ReconciliationResult(status=status, detail_sum=detail, reported_total=reported, difference=diff, tolerance=tol, selected_source=chosen.get("source"), selected_location=location, notes=notes, **base)


def dominant_currency(holdings: list[Holding]) -> tuple[str | None, bool]:
    """Reporting currency used for totals: the fair-value unit when known, else the instrument currency."""
    counts: dict[str, int] = {}
    for h in holdings:
        if h.fair_value is None:
            continue  # rows without a fair value do not participate in the fair-value reconciliation
        cur = h.reporting_currency or (h.currency if h.source_method == "html_only" else None)
        if cur:
            counts[cur] = counts.get(cur, 0) + 1
    if not counts:
        return None, False
    top = max(sorted(counts), key=lambda c: counts[c])
    return top, len(counts) > 1


def apply_row_rules(holdings: list[Holding], cfg: ValidationConfig, allow_negative_fair_value: bool | None = None) -> None:
    """SPEC 16.3 row-level checks that attach review flags."""
    allow_negative = cfg.allow_negative_fair_value if allow_negative_fair_value is None else allow_negative_fair_value
    seen_ids: dict[str, int] = {}
    for h in holdings:
        seen_ids[h.holding_id] = seen_ids.get(h.holding_id, 0) + 1
    for h in holdings:
        if not h.issuer and not h.description:
            h.add_flag("no_issuer_and_no_description")
        if seen_ids[h.holding_id] > 1:
            h.add_flag("duplicate_holding_id")
        if h.fair_value is not None and h.fair_value < 0 and not allow_negative:
            h.add_flag("negative_fair_value")
        if h.issue_date and h.maturity_date and h.maturity_date < h.issue_date:
            h.add_flag("maturity_before_issue_date")
        if h.spread is not None and not (cfg.spread_min <= h.spread <= cfg.spread_max):
            h.add_flag("spread_out_of_bounds")
        for fld in ("rate_floor", "pik_rate", "cash_rate", "percent_of_net_assets"):
            v = getattr(h, fld)
            if isinstance(v, (int, float)) and abs(v) > 1.0:
                h.add_flag(f"probable_unit_error:{fld}")
        if isinstance(h.interest_rate, (int, float)) and abs(h.interest_rate) > 1.0:
            h.add_flag("probable_unit_error:interest_rate")
        if h.fair_value is not None and h.principal_amount not in (None, 0) and h.fair_value > 1.5 * abs(h.principal_amount) and h.fair_value > 1000:
            h.add_flag("fair_value_much_larger_than_principal")
        stmt_currency = h.reporting_currency or (h.currency if h.source_method == "html_only" else None)
        if stmt_currency and cfg.expected_currencies and stmt_currency not in cfg.expected_currencies:
            h.add_flag(f"unexpected_currency:{stmt_currency}")
        if h.extraction_confidence < cfg.low_confidence_threshold:
            h.add_flag("low_confidence")


@dataclass
class ReviewItem:
    cik: str
    accession_number: str
    level: str  # filing | holding
    holding_id: str | None
    reason: str
    detail: str

    def to_row(self) -> dict[str, Any]:
        return self.__dict__.copy()


def build_review_queue(cik: str, accession: str, holdings: list[Holding], reconciliations: list[ReconciliationResult], filing_flags: list[str]) -> list[ReviewItem]:
    items: list[ReviewItem] = []
    for flag in filing_flags:
        items.append(ReviewItem(cik, accession, "filing", None, flag.split(":")[0], flag))
    for r in reconciliations:
        if r.status in {"fail", "ambiguous_total", "review"}:
            items.append(ReviewItem(cik, accession, "filing", None, f"reconciliation_{r.status}", f"{r.field}: detail={r.detail_sum} reported={r.reported_total} diff={r.difference}"))
    for h in holdings:
        for flag in h.review_flags:
            items.append(ReviewItem(cik, accession, "holding", h.holding_id, flag.split(":")[0], f"{flag} | {h.issuer} | {h.description}"))
    return items


_LEGAL_RE = re.compile(r"\b(?:inc|llc|l\.?l\.?c|lp|l\.?p|ltd|corp|corporation|co|plc|sa|s\.?a|sarl|s\.?a\.?r\.?l|bv|b\.?v|gmbh|limited|incorporated|company|holdings?)\b\.?", re.IGNORECASE)
_SEQ_SUFFIX_RE = re.compile(r"\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|[ivx]+)$", re.IGNORECASE)
_NUMERIC_FIELDS = {"cost", "amortized_cost", "fair_value", "principal_amount", "face_amount", "shares", "spread", "spread_bps", "interest_rate", "cash_rate", "pik_rate", "rate_floor", "percent_of_net_assets", "maturity_date", "issue_date"}
_SEMANTIC_FIELDS = {"affiliate_status", "controlled_status", "investment_type", "industry", "sector", "country", "reference_index", "currency", "reporting_currency"}


def _fmt_key(value: Any) -> str:
    t = str(value or "").lower().replace("&", " and ")
    t = _LEGAL_RE.sub(" ", t)
    t = _SEQ_SUFFIX_RE.sub("", t.strip())
    return re.sub(r"[^a-z0-9]+", "", t)


def classify_conflict(field_name: str, selected: Any, alternatives: list[dict[str, Any]], reason: str = "") -> str:
    """formatting | identity | semantic | numeric. 'formatting' covers disagreements that vanish under case,
    punctuation, legal-suffix, '&'/'and', whitespace and trailing sequence-number normalisation, and label containment
    (the selected name appears verbatim inside the alternative label or vice versa). Raw values stay in the conflict."""
    if field_name in _NUMERIC_FIELDS:
        return "numeric"
    sel = _fmt_key(selected)
    alts = [_fmt_key(a.get("value")) for a in alternatives]
    containment_ok = field_name in {"issuer", "description"}  # label containment is formatting only for name fields
    def same(a: str) -> bool:
        if a == sel:
            return True
        if containment_ok:
            return bool(sel) and (sel in a or a in sel)
        # vocabulary fields: a longer form of the same phrase ('... Investments') is formatting; 'Controlled' inside
        # 'Non-controlled ...' is not
        return bool(sel) and bool(a) and (a.startswith(sel) or sel.startswith(a))
    if alts and all(same(a) for a in alts):
        return "formatting"
    if field_name in _SEMANTIC_FIELDS:
        return "semantic"
    return "identity"


def classify_conflicts(holdings: list[Holding]) -> None:
    for h in holdings:
        counts: dict[str, int] = {}
        for c in h.field_conflicts:
            c.conflict_class = classify_conflict(c.field, c.selected, c.alternatives, c.reason)
            counts[c.conflict_class] = counts.get(c.conflict_class, 0) + 1
        h.conflict_classes = counts
