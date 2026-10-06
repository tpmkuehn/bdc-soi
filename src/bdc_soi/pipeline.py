"""Per-filing extraction pipeline with phase-isolated error handling (SPEC 23)."""

from __future__ import annotations

import logging
import re
import traceback
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

from bdc_soi import ENGINE_VERSION
from bdc_soi.axis_discovery import AxisScore, score_axes, select_holding_axis
from bdc_soi.composite_parser import RateResult, apply_composite_rule, parse_rate_text
from bdc_soi.concept_mapping import ConceptMapper
from bdc_soi.config import AppConfig
from bdc_soi.confidence import compute_confidence
from bdc_soi.filing_discovery import DiscoveryResult, discover_filings, find_filing
from bdc_soi.filing_package import FilingPackage, load_cached_package, retrieve_package
from bdc_soi.html_tables import HtmlExtraction, HtmlRow, TableResult, extract_html
from bdc_soi.hybrid_matcher import MatchRecord, enrich_from_row, match_holdings
from bdc_soi.identity import assign_ids, deduplicate
from bdc_soi.models import DATE_FIELDS, ErrorRecord, FactRecord, FieldConflict, FilingDiagnostic, FilingRecord, Holding
from bdc_soi.normalization import coerce_value, normalize_description, normalize_issuer
from bdc_soi.role_discovery import RoleRecord, discover_roles
from bdc_soi.sec_client import OfflineCacheMiss, SecClient, normalize_accession, normalize_cik
from bdc_soi.templates import CompositeField, TemplateRegistry, TemplateVersion
from bdc_soi.validation import assign_reconciliation_scope, classify_conflicts, ReconciliationResult, ReviewItem, TOTAL_FIELDS, apply_row_rules, build_review_queue, dominant_currency, reconcile_field
from bdc_soi.xbrl_holdings import build_xbrl_holdings
from bdc_soi.xbrl_inventory import Inventory, build_inventory
from bdc_soi.xbrl_loader import load_model

log = logging.getLogger(__name__)


class _HtmlDisabled(Exception):
    """Raised internally when a template declares HTML extraction unsupported for its layout."""


@dataclass
class RunContext:
    config: AppConfig
    registry: TemplateRegistry
    client: SecClient
    cache_dir: Path
    offline: bool = False
    today: date | None = None


@dataclass
class FilingResult:
    cik: str
    accession_number: str | None
    diagnostic: FilingDiagnostic
    filing: FilingRecord | None = None
    discovery: DiscoveryResult | None = None
    package: FilingPackage | None = None
    template: TemplateVersion | None = None
    template_reason: str = ""
    holdings: list[Holding] = field(default_factory=list)
    removed_duplicates: list[Holding] = field(default_factory=list)
    facts: list[FactRecord] = field(default_factory=list)
    axis_scores: list[AxisScore] = field(default_factory=list)
    roles: list[RoleRecord] = field(default_factory=list)
    tables: list[TableResult] = field(default_factory=list)
    html_rows: list[HtmlRow] = field(default_factory=list)
    matches: list[MatchRecord] = field(default_factory=list)
    reconciliations: list[ReconciliationResult] = field(default_factory=list)
    review_items: list[ReviewItem] = field(default_factory=list)
    total_candidates: list[dict[str, Any]] = field(default_factory=list)
    errors: list[ErrorRecord] = field(default_factory=list)
    filing_flags: list[str] = field(default_factory=list)
    inspection: dict[str, Any] = field(default_factory=dict)
    unmapped_concepts: list[dict[str, Any]] = field(default_factory=list)
    excluded_candidates: list[Any] = field(default_factory=list)

    def record_error(self, phase: str, exc: BaseException) -> None:
        rec = ErrorRecord(cik=self.cik, accession_number=self.accession_number, phase=phase, exception_type=type(exc).__name__, message=str(exc), traceback=traceback.format_exc())
        self.errors.append(rec)
        self.diagnostic.errors.append({"phase": phase, "type": rec.exception_type, "message": rec.message})
        log.error("filing %s/%s phase=%s %s: %s", self.cik, self.accession_number, phase, rec.exception_type, rec.message)
        log.debug("%s", rec.traceback)


# ---------------------------------------------------------------------------
# Composite and override helpers
# ---------------------------------------------------------------------------


def _rate_parser_for(template: TemplateVersion | None) -> Callable[[str], RateResult]:
    parser = None
    norm = template.normalization if template else None
    if template:
        parser = template.html.rate_parser
        if parser is None:
            for cf in template.composite_fields:
                if cf.rate_parser:
                    parser = cf.rate_parser
                    break
    return lambda text: parse_rate_text(text, parser, norm)


def apply_composites_to_holding(h: Holding, rules: list[CompositeField], template: TemplateVersion | None) -> None:
    """Apply XBRL-side composite rules to raw source text (member label or raw issuer) (SPEC 13.2)."""
    norm = template.normalization if template else None
    matched_any = False
    applicable = 0
    for rule in rules:
        if rule.applies_to == "html":
            continue
        if rule.source_field == "issuer":
            source_text = h.issuer_name_raw
        elif rule.source_field == "description":
            source_text = h.description_raw
        else:
            source_text = getattr(h, rule.source_field, None)
        if not source_text:
            continue
        applicable += 1
        independent_industry = h.industry if h.field_lineage.get("industry") and h.field_lineage["industry"].source != "parsed_composite_text" else None
        res = apply_composite_rule(rule, str(source_text), norm, independent_industry)
        for d in res.diagnostics:
            if any(k in d for k in ("unknown", "unresolved", "unparsed", "ambiguous", "invalid", "unspecified")):
                h.add_flag(f"composite:{rule.id}:{d}")
        if not res.matched:
            continue
        matched_any = True
        for fld, pf in res.fields.items():
            existing = h.field_lineage.get(fld)
            direct = existing is not None and existing.source == "xbrl_fact"
            same_source_label = existing is not None and existing.source == "xbrl_dimension_member" and fld == rule.source_field
            if direct and rule.precedence == "direct_first":
                if pf.value is not None and str(pf.value) != str(getattr(h, fld)):
                    cur = getattr(h, fld)
                    h.field_conflicts.append(FieldConflict(field=fld, selected=cur if not isinstance(cur, date) else cur.isoformat(), alternatives=[{"source": "parsed_composite_text", "rule_id": rule.id, "value": pf.value if not isinstance(pf.value, date) else pf.value.isoformat()}], reason="direct_value_differs_from_composite_parse"))
                    h.add_flag(f"composite_conflict:{fld}")
                continue
            if existing is not None and not same_source_label and existing.source not in {"xbrl_dimension_member", "carry_forward"} and rule.precedence == "direct_first" and getattr(h, fld) is not None:
                continue
            h.set_field(fld, pf.value, source="parsed_composite_text", raw_value=pf.raw, rule_id=rule.id, source_ref=rule.source_field, transformation=pf.transformation)
        if "issuer" in res.fields and h.issuer_name_raw is None:
            h.issuer_name_raw = str(source_text)
    if applicable and not matched_any:
        h.add_flag("composite_no_match:" + ",".join(r.id for r in rules if r.applies_to != "html"))  # unknown composite format (SPEC 18.2)


def apply_composites_to_row(row: HtmlRow, rules: list[CompositeField], template: TemplateVersion | None) -> None:
    norm = template.normalization if template else None
    for rule in rules:
        if rule.applies_to == "xbrl":
            continue
        source_text = row.fields.get(rule.source_field)
        if not isinstance(source_text, str) or not source_text:
            continue
        res = apply_composite_rule(rule, source_text, norm, row.fields.get("industry") if isinstance(row.fields.get("industry"), str) else None)
        if not res.matched:
            continue
        row.notes.append(f"composite_rule:{rule.id}")
        for fld, pf in res.fields.items():
            if row.fields.get(fld) in (None, "") or fld == rule.source_field:
                row.fields[fld] = pf.value.isoformat() if isinstance(pf.value, date) else pf.value
                row.fields_raw.setdefault(fld, pf.raw)


def apply_overrides(h: Holding, template: TemplateVersion | None) -> None:
    """Apply reviewed overrides only on exact accession/report-date/identity criteria (SPEC 8.3)."""
    if not template:
        return
    for ov in template.overrides:
        m = ov.match
        if h.report_date != m.report_date:
            continue
        if m.accession_number and normalize_accession(m.accession_number) != h.accession_number:
            continue
        if m.issuer_name_raw is not None and (h.issuer_name_raw or "") != m.issuer_name_raw:
            continue
        if m.description_raw is not None and (h.description_raw or "") != m.description_raw:
            continue
        if m.holding_member_key is not None and h.holding_member_key != m.holding_member_key:
            continue
        if m.holding_id is not None and h.holding_id != m.holding_id:
            continue
        for fld, value in ov.set.items():
            coerced, diag = coerce_value(fld, value, template.normalization.date_formats)
            if diag:
                h.add_flag(f"override_value_invalid:{ov.id}:{fld}:{diag}")
                continue
            h.set_field(fld, coerced, source="reviewed_override", raw_value=value, rule_id=ov.id, source_ref=f"{ov.provenance.source_type}:{ov.provenance.source_reference}", transformation=f"reviewed_by={ov.provenance.reviewed_by};reviewed_at={ov.provenance.reviewed_at.isoformat()}")
        h.add_flag(f"override_applied:{ov.id}")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def coerce_html_rate_fields(fields: dict[str, Any], template: TemplateVersion | None) -> dict[str, Any]:
    """Normalize HTML rate-like cells: ``5.00%`` spreads -> decimal + bps, ``8.73%`` rates -> decimal,
    ``S+`` / ``SOFR`` index cells -> canonical index via template aliases (never a global S=SOFR assumption)."""
    from bdc_soi.composite_parser import resolve_index
    from bdc_soi.normalization import parse_number

    out = dict(fields)
    for fld in ("spread", "interest_rate", "rate_floor", "pik_rate", "cash_rate", "percent_of_net_assets"):
        v = out.get(fld)
        if isinstance(v, str) and v.strip():
            p = parse_number(v)
            if p.value is None:
                if fld == "interest_rate":
                    out["interest_rate_text"] = out.get("interest_rate_text") or v
                out[fld] = None
                continue
            if p.kind == "percent":
                out[fld] = p.value / 100.0
            elif p.kind == "bps":
                out[fld] = p.value / 10000.0
            else:
                out[fld] = p.value / 100.0 if fld != "percent_of_net_assets" or p.value > 1 else p.value
    if isinstance(out.get("spread"), (int, float)) and out.get("spread_bps") in (None, ""):
        out["spread_bps"] = round(float(out["spread"]) * 10000.0, 6)
    ri = out.get("reference_index")
    if isinstance(ri, str) and ri.strip():
        aliases = dict(template.normalization.reference_index_aliases) if template else {}
        if template and template.html.rate_parser:
            aliases.update(template.html.rate_parser.index_aliases)
        token = ri.strip().rstrip("+").strip()
        resolved, _note = resolve_index(token, aliases)
        out["reference_index"] = resolved
    return out


def _html_row_to_holding(row: HtmlRow, base: dict[str, Any], table_id: str, template: TemplateVersion | None, rate_parse: Callable[[str], RateResult], document: str | None) -> Holding:
    h = Holding(**base)
    h.source_method = "html_only"
    h.source_document = document
    h.html_row_id = row.row_id
    h.source_table = f"{table_id}:{row.row_id}"
    legal = template.normalization.legal_suffixes if template else None
    date_formats = template.normalization.date_formats if template else None
    fields = coerce_html_rate_fields(row.fields, template)
    if isinstance(fields.get("interest_rate_text"), str):
        rr = rate_parse(fields["interest_rate_text"])
        for fld in ("reference_index", "spread", "spread_bps", "rate_floor", "pik_rate", "cash_rate", "interest_rate"):
            val = getattr(rr, fld)
            if val is not None and fields.get(fld) in (None, ""):
                fields[fld] = val
                row.fields_raw.setdefault(fld, fields["interest_rate_text"])
    for fld, val in fields.items():
        if fld == "interest_rate_text" or val in (None, ""):
            continue
        if fld == "issuer":
            h.issuer_name_raw = row.fields_raw.get("issuer", str(val))
            val = normalize_issuer(str(val), legal)
        elif fld == "description":
            h.description_raw = row.fields_raw.get("description", str(val))
            val = normalize_description(str(val))
        elif fld in DATE_FIELDS:
            val, diag = coerce_value(fld, val, date_formats)
            if diag:
                if diag != "empty":
                    h.add_flag(f"html_date_parse:{fld}:{diag}")
                continue
        if not hasattr(h, fld):
            continue
        src = "html_cell_carry_forward" if fld in row.carried else "html_cell"
        ref = f"{table_id}:{row.carried.get(fld, row.row_id)}"
        h.set_field(fld, val, source=src, raw_value=row.fields_raw.get(fld, val), source_ref=ref)
    return h


def _scope_contradictory_duplicate(h: Holding, rows: list, facts: list, report_date) -> None:
    """D46: canonical selection between contradictory candidates comes from source evidence, never from the totals.
    When the XBRL instance itself carries another identifier member that names the HTML row's issuer and description
    (a sibling member with report-date or comparative facts for the same position), the contradicting XBRL candidate
    is scoped ``contradictory_identity_duplicate`` (kept, flagged, outside the sums) and the HTML row stays the
    canonical candidate. Without such sibling evidence both candidates stay in schedule scope (double counted) so the
    discrepancy is visible. In every case the filing's acceptance is blocked until a reviewer resolves the identity."""
    from bdc_soi.normalization import text_key

    for row in rows:
        issuer = text_key(row.fields.get("issuer") if isinstance(row.fields.get("issuer"), str) else None)
        desc = text_key(row.fields.get("description") if isinstance(row.fields.get("description"), str) else None)
        if not issuer or not desc:
            continue
        siblings = {}
        for f in facts:
            for axis, label in (f.dimension_labels or {}).items():
                lk = text_key(label)
                if issuer in lk and desc in lk and label != (h.member_labels or {}).get(axis):
                    siblings.setdefault(label, set()).add(f"{f.local_name}@{f.period_end}")
        # The sibling must itself lack report-date monetary facts: the contradicting candidate's figures fill that gap.
        # A sibling that carries its own report-date fair value / cost is a different position, not evidence.
        rd = str(report_date) if report_date else None
        siblings = {lab: cs for lab, cs in siblings.items() if rd is None or not any(c.split("@")[0] in {"InvestmentOwnedAtFairValue", "InvestmentOwnedAtCost"} and c.endswith("@" + rd) for c in cs)}
        if siblings:
            label, concepts = sorted(siblings.items())[0]
            h.reconciliation_scope = "contradictory_identity_duplicate"
            h.scope_rule = "D46:contradictory_identity_duplicate"
            h.scope_evidence = (f"XBRL member '{label[:160]}' names the HTML row {row.row_id} identity ({sorted(concepts)[:6]}); "
                                f"this candidate's label contradicts the HTML issuer and description while carrying the same figures")
            h.add_flag(f"canonical_candidate_by_source_evidence:{row.row_id}")
            return


def _apply_group_level_lineage(h: Holding, m, group_rows: list, table_id: str) -> None:
    """D44: a group-equivalent pairing keeps one HTML row per XBRL row (multiplicity preserved, no double counting)
    but no row-level identity: HTML-derived fields are kept only when every row of the group carries the same value,
    with the whole group as the source reference; differing values are dropped and recorded as a conflict."""
    ids = [r.row_id for r in group_rows]
    group_ref = f"{table_id}:group[{';'.join(ids)}]"
    h.source_table = group_ref
    for fld, entry in list(h.field_lineage.items()):
        if not entry.source.startswith("html_cell"):
            continue
        values = {str(r.fields.get(fld)) for r in group_rows}
        if len(values) <= 1:
            entry.source_ref = group_ref
            entry.transformation = "group_level_identity"
        else:
            h.field_conflicts.append(FieldConflict(field=fld, selected=None, alternatives=[{"source": "html_cell", "row_id": r.row_id, "value": r.fields.get(fld)} for r in group_rows], reason="group_members_differ_no_row_identity"))
            setattr(h, fld, None)
            del h.field_lineage[fld]
            h.add_flag(f"group_field_dropped:{fld}")


def process_filing(ctx: RunContext, cik: str | int, accession: str | None = None) -> FilingResult:
    cik = normalize_cik(cik)
    acc = normalize_accession(accession) if accession else None
    diag = FilingDiagnostic(cik=cik, accession_number=acc or "")
    result = FilingResult(cik=cik, accession_number=acc, diagnostic=diag)
    cfg = ctx.config

    # ---- Phase 1: discovery ------------------------------------------------
    try:
        diag.phase = "filing_discovery"
        if acc:
            filing, discovery = find_filing(ctx.client, cik, acc, cfg.filings, ctx.today)
        else:
            discovery = discover_filings(ctx.client, cik, cfg.filings, ctx.today)
            filing = discovery.selected
        result.discovery = discovery
        result.filing = filing
        diag.company_name = discovery.company_name
        if filing is None:
            raise RuntimeError("no eligible filing found" if not acc else f"accession {acc} not found in submissions for CIK {cik}")
        acc = filing.accession_number
        result.accession_number = acc
        diag.accession_number = acc
        diag.report_date = filing.report_date
    except OfflineCacheMiss as exc:
        if acc and load_cached_package(ctx.cache_dir, cik, acc) is not None:
            diag.notes.append(f"offline:submissions_not_cached:{exc}")
            filing = None
        else:
            result.record_error("filing_discovery", exc)
            diag.status = "failed"
            return result
    except Exception as exc:
        result.record_error("filing_discovery", exc)
        diag.status = "failed"
        return result

    # ---- Phase 2: package --------------------------------------------------
    try:
        diag.phase = "package_download"
        pkg = load_cached_package(ctx.cache_dir, cik, acc) if ctx.offline else None
        if pkg is None:
            pkg = retrieve_package(ctx.client, cik, acc, filing.primary_document if filing else None)
        result.package = pkg
        diag.instance_document = pkg.instance.path.name if pkg.instance.path else None
        diag.instance_kind = pkg.instance.kind
    except Exception as exc:
        result.record_error("package_download", exc)
        diag.status = "failed"
        return result

    report_date = filing.report_date if filing else None
    form = filing.form if filing else None
    company_name = (filing.company_name if filing else None) or diag.company_name
    generic = ctx.registry.generic
    generic_tv = generic.templates[0] if generic and generic.templates else None
    families = ctx.registry.namespace_families()

    # ---- Phase 3: XBRL -----------------------------------------------------
    inventory: Inventory | None = None
    loaded = None
    xbrl_holdings: list[Holding] = []
    xbrl_totals: list[dict[str, Any]] = []
    template: TemplateVersion | None = None
    selected_axis: str | None = None
    configured_axis = False
    try:
        diag.phase = "arelle_loading"
        if pkg.instance.path is None:
            raise RuntimeError(f"no XBRL instance available: {pkg.instance.reason}")
        loaded = load_model(pkg.instance.path, ctx.cache_dir, ctx.offline)
        inventory = build_inventory(loaded.model, loaded.document_type, loaded.extension_namespaces, report_date)
        if inventory.report_date and report_date and inventory.report_date != report_date:
            diag.notes.append(f"report_date_mismatch:dei={inventory.report_date}:submissions={report_date}")
        report_date = inventory.report_date or report_date
        diag.report_date = report_date
        diag.phase = "template_selection"
        template, result.template_reason = ctx.registry.select(cik, report_date, form, acc) if report_date else (None, "no_report_date")
        result.template = template
        diag.template_id = template.id if template else (generic_tv.id if generic_tv else None)
        xspec = template.xbrl if template else None
        gspec = generic_tv.xbrl if generic_tv else None
        diag.phase = "role_discovery"
        roles = discover_roles(loaded.model, (xspec.role_regex if xspec else []) + (gspec.role_regex if gspec else []))
        result.roles = roles.roles
        diag.phase = "concept_mapping"
        mapper = ConceptMapper.build(xspec, gspec, families, inventory.extension_namespaces)
        unmapped: dict[str, dict[str, Any]] = {}
        for f in inventory.facts:
            m = mapper.map_concept(f.concept_clark, f.namespace, f.local_name, f.standard_label, f.documentation_label)
            f.mapped_field, f.mapping_rule = m.field, m.rule
            f.soi_roles = roles.soi_concepts.get(f.concept_clark, [])
            f.in_soi_role = bool(f.soi_roles)
            if m.field is None and f.in_soi_role and f.concept_clark not in unmapped:
                unmapped[f.concept_clark] = {"concept": f.concept_clark, "label": f.standard_label, "data_type": f.data_type}
        result.unmapped_concepts = [unmapped[k] for k in sorted(unmapped)]
        result.facts = inventory.facts
        diag.phase = "holding_axis_selection"
        scores = score_axes(inventory.facts, report_date, inventory.axes, roles.soi_axes, xspec.row_axes if xspec else (gspec.row_axes if gspec else None), mapper.families, cfg.validation.min_axis_members)
        best, axis_reason = select_holding_axis(scores)
        result.axis_scores = scores
        selected_axis = best.axis if best else None
        configured_axis = bool(best and best.template_match)
        diag.selected_axis = selected_axis
        if best is None:
            diag.notes.append(f"axis:{axis_reason}")
            result.filing_flags.append(f"no_selected_holding_axis:{axis_reason}")
        elif best.member_count < cfg.validation.min_axis_members:
            result.filing_flags.append(f"holding_axis_few_members:{best.member_count}")
        diag.phase = "context_grouping"
        base = dict(cik=cik, company_name=company_name, accession_number=acc, filing_date=filing.filing_date if filing else None, report_date=report_date, form=form, template_id=diag.template_id, engine_version=ENGINE_VERSION)
        xe = build_xbrl_holdings(inventory.facts, report_date, selected_axis, mapper, xspec, gspec, mapper.families, base, template.normalization.legal_suffixes if template else None, template.normalization.date_formats if template else None, pkg.instance.path.name)
        xbrl_holdings = xe.holdings
        for h in xbrl_holdings:
            h._in_soi_role = any(fid in roles.soi_concepts for fid in h.source_concepts.values())  # type: ignore[attr-defined]
        xbrl_totals = [t.to_dict() for t in xe.totals]
        result.excluded_candidates = xe.excluded
        diag.notes.extend(xe.notes)
        for n in xe.notes:
            if n.startswith("xbrl_groups_without_monetary_values_excluded"):
                result.filing_flags.append(n)
        n_parents = sum(1 for n in xe.notes if n.startswith("xbrl_parent_member_excluded"))
        if n_parents:
            result.filing_flags.append(f"xbrl_parent_members_excluded:{n_parents}")
        n_tmpl = sum(1 for n in xe.notes if n.startswith("xbrl_member_excluded_by_template"))
        if n_tmpl:
            result.filing_flags.append(f"xbrl_members_excluded_by_template:{n_tmpl}")
        n_aff = sum(1 for n in xe.notes if n.startswith("xbrl_affiliate_schedule_member_excluded"))
        if n_aff:
            result.filing_flags.append(f"xbrl_affiliate_schedule_members_excluded:{n_aff}")
        n_nonh = sum(1 for n in xe.notes if n.startswith("xbrl_non_holding_member_excluded"))
        if n_nonh:
            result.filing_flags.append(f"xbrl_non_holding_members_excluded:{n_nonh}")
        diag.xbrl_holdings = len(xbrl_holdings)
        diag.xbrl_status = "ok" if xbrl_holdings else ("no_holdings" if selected_axis else "no_axis")
        diag.phase = "composite_parsing"
        for h in xbrl_holdings:
            apply_composites_to_holding(h, template.composite_fields if template else [], template)
    except Exception as exc:
        result.record_error(diag.phase or "xbrl", exc)
        diag.xbrl_status = f"failed:{diag.phase}"
    finally:
        if loaded is not None:
            loaded.close()

    if template is None and report_date is not None and result.template_reason == "":
        try:
            template, result.template_reason = ctx.registry.select(cik, report_date, form, acc)
            result.template = template
            diag.template_id = template.id if template else (generic_tv.id if generic_tv else None)
        except Exception as exc:
            result.record_error("template_selection", exc)
    if result.template_reason.startswith(("no_", "only_")):
        result.filing_flags.append(f"template_mismatch:{result.template_reason}")

    base = dict(cik=cik, company_name=company_name, accession_number=acc, filing_date=filing.filing_date if filing else None, report_date=report_date, form=form, template_id=diag.template_id, engine_version=ENGINE_VERSION)
    rate_parse = _rate_parser_for(template)

    # ---- Phase 4: HTML -----------------------------------------------------
    html: HtmlExtraction | None = None
    try:
        diag.phase = "html_table_detection"
        if pkg.primary_path is None:
            raise RuntimeError("no primary HTML document in package")
        hspec = template.html if template else (generic_tv.html if generic_tv else None)
        if template and template.html.disabled:
            diag.html_status = "disabled_by_template"
            diag.notes.append(f"html_disabled_by_template:{template.html.disabled_reason}")
            result.filing_flags.append("html_disabled_by_template")
            raise _HtmlDisabled()
        known: dict[str, set[str]] = {}
        for h in xbrl_holdings:
            for fld in ("industry", "investment_type", "affiliate_status", "sector"):
                le = h.field_lineage.get(fld)
                if le and le.source == "xbrl_dimension_member" and getattr(h, fld):
                    known.setdefault(fld, set()).add(str(getattr(h, fld)))
        # Classification vocabularies disclosed anywhere in the instance (industry subtotals etc.).
        from bdc_soi.concept_mapping import extract_qname_parts as _qp
        from bdc_soi.xbrl_holdings import GENERIC_DIMENSION_FIELDS as _GDF

        for f in (inventory.facts if inventory else []):
            for axis, label in f.dimension_labels.items():
                local = _qp(axis)[1]
                for pat, fld in _GDF:
                    if fld in {"industry", "investment_type", "affiliate_status"} and pat.search(local) and label:
                        known.setdefault(fld, set()).add(re.sub(r"\s*\[Member\]\s*$", "", label))
                        break
        # The template's own industry vocabulary (composite header parsers) is evidence-grounded and is
        # recognised in HTML headings even when the instance's industry axis uses other sector names.
        for cf in (template.composite_fields if template else []):
            if cf.header_parser and cf.header_parser.known_industries:
                known.setdefault("industry", set()).update(cf.header_parser.known_industries)
        if template and template.html.row_rules.known_industries:
            known.setdefault("industry", set()).update(template.html.row_rules.known_industries)
        html = extract_html(pkg.primary_path, report_date, hspec, known_group_values=known, template_is_company=template is not None)
        result.tables = html.tables
        for row in html.holding_rows:
            apply_composites_to_row(row, template.composite_fields if template else [], template)
        result.html_rows = html.holding_rows
        diag.html_rows = len(html.holding_rows)
        # Scale cross-check (diagnostic only): compare the median HTML fair value with the median XBRL fair value.
        xfv = sorted(abs(h.fair_value) for h in xbrl_holdings if h.fair_value)
        hfv = sorted(abs(r.fields["fair_value"]) for r in html.holding_rows if isinstance(r.fields.get("fair_value"), (int, float)) and r.fields.get("fair_value"))
        if xfv and hfv:
            ratio = xfv[len(xfv) // 2] / hfv[len(hfv) // 2]
            if ratio > 50 or ratio < 1 / 50:
                result.filing_flags.append(f"html_scale_mismatch_vs_xbrl:median_ratio={ratio:.1f}")
        diag.html_status = "ok" if html.holding_rows else "no_rows"
        if not any(t.accepted for t in html.tables):
            result.filing_flags.append("html_no_soi_table_accepted")
    except _HtmlDisabled:
        html = None
    except Exception as exc:
        result.record_error("html_table_detection", exc)
        diag.html_status = "failed"

    # ---- Phase 5: matching -------------------------------------------------
    holdings: list[Holding] = list(xbrl_holdings)
    assign_ids(holdings)
    matches: list[MatchRecord] = []
    table_ids = {}
    if html:
        for t in html.tables:
            for r in t.rows:
                table_ids[r.row_id] = t.table_id
    match_status: dict[str, str] = {}
    doc_units = sorted({t.get("unit") for t in xbrl_totals if t.get("field") == "fair_value" and t.get("rank", 9) <= 1 and t.get("unit")})
    document_currency = doc_units[0] if len(doc_units) == 1 else None
    try:
        diag.phase = "xbrl_html_matching"
        if holdings and html and html.holding_rows:
            matches = match_holdings(holdings, html.holding_rows, cfg.matching)
            rows_by_id = {r.row_id: r for r in html.holding_rows}
            consumed = {m.html_row_id for m in matches if m.status == "matched" and m.html_row_id}
            for h, m in zip(holdings, matches):
                match_status[h.holding_id] = m.status
                if m.status == "matched" and m.html_row_id:
                    row = rows_by_id[m.html_row_id]
                    enrich_from_row(h, row, m, table_ids.get(row.row_id, "table"), rate_parse, template.html.prefer_html_fields if template else None, template, document_currency)
                    if m.group_row_ids:
                        _apply_group_level_lineage(h, m, [rows_by_id[r] for r in m.group_row_ids if r in rows_by_id], table_ids.get(row.row_id, "table"))
                elif m.status == "ambiguous":
                    h.add_flag("ambiguous_html_match")
                elif m.status == "unmatched" and m.reason.startswith("contradictory_identity:"):
                    # Equal money under a different issuer and description is a contradiction only while the HTML row
                    # itself has no consistent identity elsewhere; a row consumed by its own XBRL member is a value
                    # coincidence (Crescent: Hercules common stock cost = RWA Wealth Partners' cost) and the XBRL row is
                    # simply XBRL-only. Both candidates stay; nothing is merged; acceptance is blocked until resolved.
                    open_rows = [rid for rid in m.reason.split(":", 1)[1].split(";") if rid not in consumed]
                    if open_rows:
                        h.add_flag(f"contradictory_identity_candidate:{';'.join(open_rows)}")
                    else:
                        h.add_flag("value_coincidence_with_matched_html_row:" + m.reason.split(":", 1)[1])
            contradicted_rows: dict[str, str] = {}
            for h, m in zip(holdings, matches):
                open_rows = [f.split(":", 1)[1] for f in h.review_flags if f.startswith("contradictory_identity_candidate:")]
                if open_rows:
                    rids = open_rows[0].split(";")
                    for rid in rids:
                        contradicted_rows[rid] = h.holding_id
                    _scope_contradictory_duplicate(h, [rows_by_id[r] for r in rids if r in rows_by_id], result.facts, report_date)
            matched_ids = {m.html_row_id for m in matches if m.html_row_id}
            diag.matched_rows = len(matched_ids)
            unmatched = [r for r in html.holding_rows if r.row_id not in matched_ids]
            diag.unmatched_html_rows = len(unmatched)
            if cfg.extraction.append_unmatched_html_rows:
                for r in unmatched:
                    h = _html_row_to_holding(r, base, table_ids.get(r.row_id, "table"), template, rate_parse, pkg.primary_document)
                    h.add_flag("unmatched_html_row")
                    if r.row_id in contradicted_rows:
                        h.add_flag(f"contradictory_identity_candidate:{contradicted_rows[r.row_id]}")
                    if "after_total_row" in r.notes:
                        h.add_flag("html_row_after_total")  # listed after the grand total (e.g. cash equivalents)
                    holdings.append(h)
        elif html and html.holding_rows and not holdings:
            diag.unmatched_html_rows = len(html.holding_rows)
            for r in html.holding_rows:
                h = _html_row_to_holding(r, base, table_ids.get(r.row_id, "table"), template, rate_parse, pkg.primary_document)
                h.add_flag("html_fallback_no_xbrl_holdings")
                holdings.append(h)
        result.matches = matches
    except Exception as exc:
        result.record_error("xbrl_html_matching", exc)

    # ---- Phase 6: overrides, identity, validation ---------------------------
    try:
        diag.phase = "normalization"
        assign_ids(holdings)
        for h in holdings:
            apply_overrides(h, template)
        diag.phase = "deduplication"
        dd = deduplicate(holdings)
        holdings = dd.kept
        result.removed_duplicates = dd.removed
        diag.phase = "validation"
        for h in holdings:
            compute_confidence(h, configured_axis=configured_axis, match_status=match_status.get(h.holding_id))
        contradictions = [h for h in holdings if any(f.startswith("contradictory_identity_candidate") for f in h.review_flags)]
        if contradictions:
            result.filing_flags.append(f"acceptance_blocked:unresolved_identity_contradiction:{len(contradictions)}_candidates")
        row_texts = {r.row_id: r.row_text for r in html.holding_rows} if html and html.holding_rows else {}
        section_headings = {r.row_id: " | ".join(str(v) for v in (r.group_context or {}).values() if v) for r in html.holding_rows} if html and html.holding_rows else {}
        assign_reconciliation_scope(holdings, row_texts, section_headings)
        apply_row_rules(holdings, cfg.validation, template.validation.allow_negative_fair_value if template else None)
        classify_conflicts(holdings)
        currency, mixed = dominant_currency(holdings)
        if mixed:
            result.filing_flags.append("mixed_currencies_no_conversion_rule")
            if len({h.reporting_currency for h in holdings if h.reporting_currency}) <= 1:
                mixed = False  # instrument currencies differ but all fair values are stated in one reporting currency
                result.filing_flags[-1] = "mixed_instrument_currencies_single_reporting_currency"
        candidates = list(xbrl_totals) + ([t.to_dict() for t in html.totals] if html else [])
        result.total_candidates = candidates
        diag.phase = "total_selection"
        recs: list[ReconciliationResult] = []
        for fld in TOTAL_FIELDS:
            rr = reconcile_field(fld, holdings, candidates, cfg.validation, currency, template.validation.total_source_preference if template else None, report_date.isoformat() if report_date else None)
            if mixed and rr.status == "pass":
                rr.status = "review"
                rr.notes.append("mixed currencies in holdings; no conversion rule")
            recs.append(rr)
        result.reconciliations = recs
        diag.fair_value_reconciliation = recs[0].status
        diag.cost_reconciliation = recs[1].status
        diag.amortized_cost_reconciliation = recs[2].status
        n_conf = sum(1 for h in holdings if h.field_conflicts)
        diag.conflicts = n_conf
        if holdings and n_conf / len(holdings) > cfg.validation.max_conflict_ratio:
            result.filing_flags.append(f"excessive_field_conflicts:{n_conf}/{len(holdings)}")
        if xbrl_holdings and diag.html_rows and diag.unmatched_html_rows / max(1, diag.html_rows) > cfg.validation.max_unmatched_html_ratio:
            result.filing_flags.append(f"excessive_unmatched_html_rows:{diag.unmatched_html_rows}/{diag.html_rows}")
        if not holdings:
            result.filing_flags.append("no_holdings")
        for h in holdings:
            if any(f.startswith("composite:") for f in h.review_flags):
                pass
        result.review_items = build_review_queue(cik, acc, holdings, recs, result.filing_flags)
    except Exception as exc:
        result.record_error(diag.phase or "validation", exc)

    result.holdings = holdings
    diag.holdings_count = len(holdings)
    if diag.errors:
        diag.status = "partial" if holdings else "failed"
    else:
        diag.status = "ok"
    diag.phase = "done"
    result.inspection = _inspection_summary(result)
    return result


def _inspection_summary(r: FilingResult) -> dict[str, Any]:
    mapped: dict[str, set[str]] = {}
    for f in r.facts:
        if f.mapped_field:
            mapped.setdefault(f.mapped_field, set()).add(f.concept_clark)
    return {
        "cik": r.cik,
        "accession_number": r.accession_number,
        "company_name": r.diagnostic.company_name,
        "report_date": r.diagnostic.report_date.isoformat() if r.diagnostic.report_date else None,
        "template_id": r.diagnostic.template_id,
        "template_reason": r.template_reason,
        "instance": {"document": r.diagnostic.instance_document, "kind": r.diagnostic.instance_kind},
        "presentation_roles": [{"uri": x.uri, "definition": x.definition, "candidate": x.is_candidate, "concepts": x.concept_count} for x in r.roles],
        "mapped_concepts": {k: sorted(v) for k, v in sorted(mapped.items())},
        "unmapped_soi_concepts": r.unmapped_concepts,
        "candidate_holding_axes": [a.to_row() for a in sorted(r.axis_scores, key=lambda a: (-a.score, a.axis))],
        "selected_axis": r.diagnostic.selected_axis,
        "html_table_scores": [t.to_row() for t in sorted(r.tables, key=lambda t: (-t.score, t.table_index))[:40]],
        "inferred_column_mappings": {t.table_id: {str(k): v for k, v in sorted(t.column_mapping.items())} for t in r.tables if t.accepted},
        "example_rows": [row for t in r.tables if t.accepted for row in t.example_rows][:10],
        "example_holdings": [h.to_row() for h in r.holdings[:5]],
        "reported_total_candidates": r.total_candidates,
        "reconciliation": [x.to_row(r.cik, r.accession_number or "") for x in r.reconciliations],
        "filing_flags": r.filing_flags,
        "errors": [e.model_dump(exclude={"traceback"}) for e in r.errors],
    }
