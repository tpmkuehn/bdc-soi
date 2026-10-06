"""One-to-one XBRL/HTML matching with feature scores and margins (SPEC 14)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from rapidfuzz import fuzz

from bdc_soi.config import MatchingConfig
from bdc_soi.html_tables import HtmlRow
from bdc_soi.models import FieldConflict, Holding, LineageEntry
from bdc_soi.normalization import text_key

NUMERIC_FEATURES = (("fair_value", 3.0), ("cost", 2.0), ("amortized_cost", 2.0), ("principal_amount", 2.0), ("face_amount", 1.5), ("shares", 2.0))
TEXT_FEATURES = (("issuer", 2.0), ("description", 1.0))
ENRICHABLE_FIELDS = (
    "issuer", "description", "industry", "sector", "country", "investment_type", "reference_index", "spread", "spread_bps",
    "cash_rate", "pik_rate", "rate_floor", "interest_rate", "issue_date", "maturity_date", "principal_amount", "face_amount",
    "shares", "cost", "amortized_cost", "fair_value", "percent_of_net_assets", "currency", "affiliate_status", "controlled_status",
    "footnote_markers",
)


@dataclass
class MatchRecord:
    holding_id: str
    holding_member_key: str | None
    html_row_id: str | None
    status: str  # matched | ambiguous | unmatched | no_candidates
    best_score: float
    second_score: float | None
    margin: float | None
    matched_features: dict[str, float] = field(default_factory=dict)
    conflicting_fields: list[str] = field(default_factory=list)
    enrichment_fields: list[str] = field(default_factory=list)
    reason: str = ""
    group_row_ids: list[str] = field(default_factory=list)  # D44: HTML rows of a group-equivalent pairing

    def to_row(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["matched_features"] = json.dumps(self.matched_features, sort_keys=True)
        d["conflicting_fields"] = json.dumps(self.conflicting_fields)
        d["enrichment_fields"] = json.dumps(self.enrichment_fields)
        return d


def _num_close(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= max(1.0, abs(a) * 1e-4)


def _num_key(v: float | None) -> int | None:
    return None if v is None else int(round(v))


def score_pair(h: Holding, row: HtmlRow) -> tuple[float, dict[str, float], str | None]:
    """Score a candidate pair; returns (score, features, rejection_reason)."""
    feats: dict[str, float] = {}
    numeric_hits = 0
    nonzero_hits = 0
    for fld, weight in NUMERIC_FEATURES:
        hv = getattr(h, fld)
        rv = row.fields.get(fld)
        if hv is not None and isinstance(rv, (int, float)) and _num_close(float(hv), float(rv)):
            feats[fld] = weight
            numeric_hits += 1
            if abs(float(hv)) > 0:
                nonzero_hits += 1
    if any(n.startswith("combined_par_shares") for n in row.notes) and "principal_amount" not in feats and "shares" not in feats:
        # A combined 'Principal Amount / Shares' column: the HTML side can only guess which it holds; compare the
        # value against the other XBRL quantity too (Investcorp equity rows quote a PIK rate, so the share count
        # landed in principal; Commonwealth units are tagged as principal in XBRL).
        rv_p, rv_s = row.fields.get("principal_amount"), row.fields.get("shares")
        if h.shares is not None and isinstance(rv_p, (int, float)) and _num_close(float(h.shares), float(rv_p)):
            feats["shares_via_combined_column"] = 2.0
            numeric_hits += 1
        elif h.principal_amount is not None and isinstance(rv_s, (int, float)) and _num_close(float(h.principal_amount), float(rv_s)):
            feats["principal_via_combined_column"] = 2.0
            numeric_hits += 1
    issuer_sim = 0.0
    for fld, weight in TEXT_FEATURES:
        hv = text_key(getattr(h, fld))
        rv = text_key(row.fields.get(fld) if isinstance(row.fields.get(fld), str) else None)
        if hv and rv:
            sim = fuzz.token_set_ratio(hv, rv)
            if fld == "issuer":
                issuer_sim = sim
                if sim >= 90:
                    feats[fld] = weight
                    if hv == rv:
                        feats["issuer_exact"] = 1.0  # identical normalized names outrank near-identical ones (A-1 vs B-1 share classes)
                elif sim >= 75:
                    feats[fld] = weight / 2
            else:
                # Descriptions distinguish facilities ("First" vs "Second Lien"); only near-exact text scores,
                # and a clearly different description is penalized so identical monetary rows resolve correctly.
                if sim >= 95:
                    feats[fld] = weight
                elif sim >= 88 and hv.split()[0] == rv.split()[0]:
                    feats[fld] = weight / 2
                elif sim < 60:
                    feats["description_mismatch"] = -1.5
    hm = h.maturity_date
    rm = row.fields.get("maturity_date")
    if hm is not None and rm:
        try:
            rmd = date.fromisoformat(str(rm)) if not isinstance(rm, date) else rm
        except ValueError:
            rmd = None
        if rmd == hm:
            feats["maturity_date"] = 1.5
    score = sum(feats.values())
    if "description_mismatch" in feats and issuer_sim < 75 and nonzero_hits:
        # Equal NON-ZERO money with a different issuer AND a different description is contradictory identity evidence
        # (BIP: a CareSave-labelled XBRL member carrying Integrative Life Network's figures); never merged. Zero-value
        # agreement (unfunded revolvers, zero-value warrants) is no evidence either way.
        return 0.0, feats, "contradictory_identity_evidence"
    if numeric_hits == 0:
        # Text-only evidence: never match on one weak text overlap (14.3).
        strong_text = issuer_sim >= 90 and ("maturity_date" in feats or "description" in feats)
        if not strong_text:
            return 0.0, feats, "no_numeric_feature_and_weak_text"
    return score, feats, None


def match_holdings(holdings: list[Holding], rows: list[HtmlRow], cfg: MatchingConfig) -> list[MatchRecord]:
    # Pre-index HTML rows by rounded monetary values and issuer key to avoid quadratic scans.
    index: dict[tuple[str, int], set[int]] = {}
    issuer_index: dict[str, set[int]] = {}
    for i, row in enumerate(rows):
        for fld, _w in NUMERIC_FEATURES:
            v = row.fields.get(fld)
            if isinstance(v, (int, float)):
                index.setdefault((fld, _num_key(float(v))), set()).add(i)
        key = text_key(row.fields.get("issuer") if isinstance(row.fields.get("issuer"), str) else None)
        for tok in key.split():
            if len(tok) > 2:
                issuer_index.setdefault(tok, set()).add(i)
    proposals: list[tuple[float, int, int, dict[str, float], float | None]] = []
    records: dict[int, MatchRecord] = {}
    for hi, h in enumerate(holdings):
        cand: set[int] = set()
        for fld, _w in NUMERIC_FEATURES:
            v = getattr(h, fld)
            if v is not None:
                k = _num_key(float(v))
                for delta in (-1, 0, 1):
                    cand |= index.get((fld, k + delta), set())
        if not cand:
            toks = [t for t in text_key(h.issuer).split() if len(t) > 2]
            for tok in toks:
                cand |= issuer_index.get(tok, set())
        scored: list[tuple[float, int, dict[str, float]]] = []
        contradictory: list[str] = []
        for ri in sorted(cand):
            s, feats, reason = score_pair(h, rows[ri])
            if reason is None and s > 0:
                scored.append((s, ri, feats))
            elif reason == "contradictory_identity_evidence":
                contradictory.append(rows[ri].row_id)
        scored.sort(key=lambda t: (-t[0], t[1]))
        if not scored:
            if contradictory:
                records[hi] = MatchRecord(h.holding_id, h.holding_member_key, None, "unmatched", 0.0, None, None, reason=f"contradictory_identity:{';'.join(contradictory)}")
            else:
                records[hi] = MatchRecord(h.holding_id, h.holding_member_key, None, "no_candidates", 0.0, None, None, reason="no_scored_candidates")
            continue
        best_s, best_ri, best_feats = scored[0]
        second_s = scored[1][0] if len(scored) > 1 else None
        margin = None if second_s is None else round(best_s - second_s, 4)
        if best_s < cfg.minimum_score:
            records[hi] = MatchRecord(h.holding_id, h.holding_member_key, None, "unmatched", best_s, second_s, margin, best_feats, reason=f"best_below_minimum:{best_s}<{cfg.minimum_score}")
            continue
        if cfg.require_unique_best_match and margin is not None and margin < cfg.minimum_margin:
            records[hi] = MatchRecord(h.holding_id, h.holding_member_key, None, "ambiguous", best_s, second_s, margin, best_feats, reason="best_not_uniquely_better")
            continue
        proposals.append((best_s, hi, best_ri, best_feats, second_s))
    # Resolve one-to-one: higher score wins; equal scores for the same row are ambiguous.
    proposals.sort(key=lambda p: (-p[0], p[1], p[2]))
    taken_rows: dict[int, tuple[float, int]] = {}
    for s, hi, ri, feats, second_s in proposals:
        h = holdings[hi]
        prior = taken_rows.get(ri)
        if prior is not None:
            if abs(prior[0] - s) < cfg.minimum_margin:
                records[hi] = MatchRecord(h.holding_id, h.holding_member_key, None, "ambiguous", s, second_s, None, feats, reason=f"html_row_contested:{rows[ri].row_id}")
                other_hi = prior[1]
                if other_hi in records and records[other_hi].status == "matched":
                    records[other_hi].status = "ambiguous"
                    records[other_hi].html_row_id = None
                    records[other_hi].reason = f"html_row_contested:{rows[ri].row_id}"
            else:
                records[hi] = MatchRecord(h.holding_id, h.holding_member_key, None, "unmatched", s, second_s, None, feats, reason=f"html_row_taken_by_higher_score:{rows[ri].row_id}")
            continue
        taken_rows[ri] = (s, hi)
        records[hi] = MatchRecord(h.holding_id, h.holding_member_key, rows[ri].row_id, "matched", s, second_s, None if second_s is None else round(s - second_s, 4), feats)
    _sequence_tiebreak(holdings, rows, records, taken_rows, cfg)
    return [records[i] for i in range(len(holdings))]


def _sequence_tiebreak(holdings: list[Holding], rows: list[HtmlRow], records: dict[int, MatchRecord], taken_rows: dict[int, tuple[float, int]], cfg: MatchingConfig) -> None:
    """Table-sequence feature (SPEC 14.2): when an issuer has N ambiguous XBRL rows and exactly N free HTML rows with
    the same monetary values, assign them in document order (XBRL member label order vs HTML row order). Recorded as
    ``sequence_tiebreak`` with a review flag; groups whose counts differ stay ambiguous."""
    groups: dict[tuple, list[int]] = {}
    for hi, rec in records.items():
        if rec.status != "ambiguous":
            continue
        h = holdings[hi]
        key = (text_key(h.issuer), _num_key(h.fair_value), _num_key(h.cost), _num_key(h.principal_amount))
        groups.setdefault(key, []).append(hi)
    for key, his in groups.items():
        free = [ri for ri, r in enumerate(rows) if ri not in taken_rows and text_key(r.fields.get("issuer") if isinstance(r.fields.get("issuer"), str) else None) == key[0]
                and _num_key(r.fields.get("fair_value") if isinstance(r.fields.get("fair_value"), (int, float)) else None) == key[1]
                and _num_key(r.fields.get("cost") if isinstance(r.fields.get("cost"), (int, float)) else None) == key[2]]
        if len(free) != len(his) or len(his) < 2:
            continue
        # Descriptions must pair up (sorted by description key); rows without distinguishing descriptions stay ambiguous.
        his_sorted = sorted(his, key=lambda i: (text_key(holdings[i].description), holdings[i].holding_member_key or "", holdings[i].holding_id))
        free_sorted = sorted(free, key=lambda ri: (text_key(rows[ri].fields.get("description") if isinstance(rows[ri].fields.get("description"), str) else None), ri))
        pairs = list(zip(his_sorted, free_sorted))
        if not all(text_key(holdings[hi].description) and fuzz.token_set_ratio(text_key(holdings[hi].description), text_key(rows[ri].fields.get("description") if isinstance(rows[ri].fields.get("description"), str) else None)) >= 90 for hi, ri in pairs):
            continue
        # Row-level identity is demonstrable only when every description is distinct on both sides and each pair agrees
        # exactly; otherwise the pairing is arbitrary within the group (D44) and is recorded at group level.
        x_keys = [text_key(holdings[hi].description) for hi, _ in pairs]
        h_keys = [text_key(rows[ri].fields.get("description") if isinstance(rows[ri].fields.get("description"), str) else None) for _, ri in pairs]
        row_level = len(set(x_keys)) == len(pairs) and len(set(h_keys)) == len(pairs) and all(a == b for a, b in zip(x_keys, h_keys))
        group_id = "grp:" + ":".join(str(k) for k in key)
        group_rows = [rows[ri].row_id for _, ri in pairs]
        for hi, ri in pairs:
            h = holdings[hi]
            feats = dict(records[hi].matched_features)
            feats["sequence_tiebreak"] = 0.5
            score = records[hi].best_score + 0.5
            if score < cfg.minimum_score:
                continue
            taken_rows[ri] = (score, hi)
            reason = "sequence_tiebreak_row_identity" if row_level else "sequence_tiebreak_group_equivalent"
            records[hi] = MatchRecord(h.holding_id, h.holding_member_key, rows[ri].row_id, "matched", score, records[hi].second_score, 0.5, feats, reason=reason, group_row_ids=[] if row_level else list(group_rows))
            h.add_flag("matched_by_sequence_tiebreak")
            if not row_level:
                h.identity_resolution = "group"
                h.match_group_id = group_id
                h.add_flag("group_level_identity")


def _materially_different(fld: str, a: Any, b: Any) -> bool:
    if a is None or b is None:
        return False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        tol = 1.0 if fld in {"fair_value", "cost", "amortized_cost", "principal_amount", "face_amount", "shares"} else 1e-6
        return abs(float(a) - float(b)) > max(tol, abs(float(a)) * 1e-4)
    if isinstance(a, date) or isinstance(b, date):
        return str(a) != str(b)
    return text_key(str(a)) != text_key(str(b))


def enrich_from_row(h: Holding, row: HtmlRow, record: MatchRecord, table_id: str, rate_parse, prefer_html_fields: list[str] | None = None, template=None, document_currency: str | None = None) -> None:
    """Fill missing fields from the matched HTML row; record conflicts for disagreements (14.4).

    ``prefer_html_fields`` (template ``html.prefer_html_fields``) lets a directly disclosed HTML cell supersede a
    value derived from composite text or a dimension label; a direct XBRL fact is never superseded.
    """
    prefer = set(prefer_html_fields or [])
    h.source_method = "hybrid_xbrl_html"
    h.html_row_id = row.row_id
    h.source_table = f"{table_id}:{row.row_id}"
    if "after_total_row" in row.notes:
        h.add_flag("html_row_after_total")  # matched an HTML row listed after the grand total (e.g. cash equivalents)
    from bdc_soi.pipeline import coerce_html_rate_fields

    row_fields = coerce_html_rate_fields(row.fields, template)
    if "interest_rate_text" in row_fields and isinstance(row_fields["interest_rate_text"], str):
        rr = rate_parse(row_fields["interest_rate_text"])
        for fld in ("reference_index", "spread", "spread_bps", "rate_floor", "pik_rate", "cash_rate", "interest_rate"):
            val = getattr(rr, fld)
            if val is not None and fld not in row_fields:
                row_fields[fld] = val
    for fld in ENRICHABLE_FIELDS:
        rv = row_fields.get(fld)
        if rv is None or rv == "":
            continue
        if fld in {"issue_date", "maturity_date"} and isinstance(rv, str):
            try:
                rv = date.fromisoformat(rv)
            except ValueError:
                from bdc_soi.normalization import parse_date

                rv, diag = parse_date(rv)
                if rv is None:
                    if diag != "empty":
                        h.add_flag(f"html_date_parse:{fld}:{diag}")
                    continue
        hv = getattr(h, fld)
        if hv is None:
            raw = row.fields_raw.get(fld, row_fields.get("interest_rate_text") if fld in {"reference_index", "spread", "spread_bps", "rate_floor", "pik_rate", "cash_rate"} else None)
            h.set_field(fld, rv, source="html_cell", raw_value=raw if raw is not None else rv, source_ref=f"{table_id}:{row.row_id}", transformation="carry_forward" if fld in row.carried else None)
            if fld in row.carried:
                h.field_lineage[fld].source = "html_cell_carry_forward"
                h.field_lineage[fld].source_ref = f"{table_id}:{row.carried[fld]}"
            record.enrichment_fields.append(fld)
        elif _materially_different(fld, hv, rv):
            existing = h.field_lineage.get(fld)
            contained = (
                fld in {"issuer", "description", "industry"}
                and existing is not None
                and existing.source == "xbrl_dimension_member"
                and isinstance(rv, str)
                and text_key(rv)
                and text_key(rv) in text_key(str(existing.raw_value or hv))
            )
            if contained:
                prefer = set(prefer) | {fld}  # the typed label concatenates the disclosed HTML cell (docs/decisions.md D25)
            if fld in prefer and existing is not None and existing.source in {"parsed_composite_text", "xbrl_dimension_member"}:
                prior = existing.model_copy()
                raw = row.fields_raw.get(fld, rv)
                h.set_field(fld, rv, source="html_cell", raw_value=raw, source_ref=f"{table_id}:{row.row_id}", rule_id="html.prefer_html_fields", transformation="carry_forward" if fld in row.carried else None)
                if fld == "issuer":
                    from bdc_soi.normalization import normalize_issuer as _ni

                    h.issuer = _ni(str(rv))
                    h.field_lineage[fld].normalized_value = h.issuer
                h.field_conflicts.append(FieldConflict(field=fld, selected=getattr(h, fld) if not isinstance(getattr(h, fld), date) else getattr(h, fld).isoformat(), alternatives=[{"source": prior.source, "rule_id": prior.rule_id, "value": hv if not isinstance(hv, date) else hv.isoformat()}], reason="html_cell_contained_in_label" if contained else "html_preferred_over_derived_text"))
                record.enrichment_fields.append(fld)
                continue
            record.conflicting_fields.append(fld)
            h.field_conflicts.append(FieldConflict(field=fld, selected=hv if not isinstance(hv, date) else hv.isoformat(), alternatives=[{"source": "html_cell", "row_id": row.row_id, "value": rv if not isinstance(rv, date) else rv.isoformat()}], reason="xbrl_html_disagreement"))
            h.add_flag(f"xbrl_html_conflict:{fld}")
    # Reporting-currency confirmation (docs/decisions.md D24): when the fair-value fact is tagged in the
    # instrument currency but the HTML fair-value cell (stated in the document currency) equals it numerically,
    # the fact is stated in the document currency. No value is converted; the unit mismatch stays visible.
    # Reporting-currency evidence (docs/decisions.md D24, revised): the HTML fair-value column discloses its currency
    # through a symbol cell ('$' at the top of the column, carried down the column); only that disclosed symbol,
    # together with a numerically equal cell, can override the fact's unit. The XBRL unit is preserved as a conflict.
    disclosed = row.currency_symbols.get("fair_value") or {}
    html_code = disclosed.get("code") or None
    documented = list(getattr(getattr(template, "validation", None), "reporting_currency_evidence", []) or [])
    if h.reporting_currency and html_code and h.reporting_currency != html_code:
        rv = row_fields.get("fair_value")
        fv_lineage = h.field_lineage.get("fair_value")
        xbrl_unit = h.reporting_currency
        if not documented:
            # D33 revised: the column symbol alone never re-assigns the reporting currency; the XBRL unit stands.
            h.add_flag(f"xbrl_fair_value_unit_mismatch:{xbrl_unit}:html_symbol_{html_code}:no_documented_reporting_currency_evidence")
        elif isinstance(rv, (int, float)) and h.fair_value is not None and not _materially_different("fair_value", h.fair_value, rv):
            h.field_conflicts.append(FieldConflict(
                field="reporting_currency", selected=html_code,
                alternatives=[{"source": "xbrl_fact_unit", "value": xbrl_unit, "fact_id": fv_lineage.source_ref if fv_lineage else None, "xbrl_value": h.fair_value},
                              {"source": "html_cell_currency_symbol", "value": html_code, "symbol": disclosed.get("symbol"), "symbol_row_id": disclosed.get("source_row_id"), "html_value": rv, "row_id": row.row_id},
                              {"source": "template_reporting_currency_evidence", "value": html_code, "evidence": documented}],
                reason="documented_reporting_currency_evidence_overrides_xbrl_unit"))
            h.field_lineage["reporting_currency"] = LineageEntry(source="html_cell_currency_symbol", raw_value=f"{disclosed.get('symbol')} (row {disclosed.get('source_row_id')}); xbrl unit {xbrl_unit}; documented evidence: {' | '.join(documented)[:300]}", rule_id="D33", normalized_value=html_code, source_ref=f"{table_id}:{row.row_id}", transformation=f"xbrl_unit={xbrl_unit};html_symbol={disclosed.get('symbol')};values_equal;documented_evidence")
            h.add_flag(f"xbrl_fair_value_unit_mismatch:{xbrl_unit}:html_symbol_{html_code}:documented_evidence")
            h.reporting_currency = html_code
        else:
            h.add_flag(f"xbrl_fair_value_unit_mismatch:{xbrl_unit}:html_symbol_{html_code}:values_differ")
    elif h.reporting_currency and document_currency and h.reporting_currency != document_currency and not html_code:
        h.add_flag(f"xbrl_fair_value_unit_mismatch:{h.reporting_currency}:no_html_currency_evidence")
    if h.issuer_name_raw is None and isinstance(row.fields_raw.get("issuer"), str):
        h.issuer_name_raw = row.fields_raw["issuer"]
    if h.description_raw is None and isinstance(row.fields_raw.get("description"), str):
        h.description_raw = row.fields_raw["description"]
