"""Explainable confidence model (SPEC 17)."""

from __future__ import annotations

from bdc_soi.models import ConfidenceFactor, Holding

HTML_ONLY_CAP = 0.60


def compute_confidence(h: Holding, *, configured_axis: bool, match_status: str | None) -> float:
    factors: list[ConfidenceFactor] = []
    lineage = h.field_lineage
    direct_xbrl = any(e.source == "xbrl_fact" and e.rule_id and e.rule_id.startswith("template_") for e in lineage.values())
    if direct_xbrl:
        factors.append(ConfidenceFactor(factor="direct_template_mapped_xbrl_fact", adjustment=0.20))
    elif any(e.source == "xbrl_fact" for e in lineage.values()):
        factors.append(ConfidenceFactor(factor="generic_mapped_xbrl_fact", adjustment=0.15))
    if h.holding_member_key and configured_axis:
        factors.append(ConfidenceFactor(factor="member_from_configured_holding_axis", adjustment=0.15))
    elif h.holding_member_key:
        factors.append(ConfidenceFactor(factor="member_from_heuristic_holding_axis", adjustment=0.10))
    if any(e.source == "xbrl_fact" and (e.transformation or "") != "nil" for e in lineage.values()) and getattr(h, "_in_soi_role", False):
        factors.append(ConfidenceFactor(factor="concept_in_soi_role", adjustment=0.10))
    if match_status == "matched":
        factors.append(ConfidenceFactor(factor="unique_xbrl_html_match", adjustment=0.10))
    if h.issuer:
        factors.append(ConfidenceFactor(factor="issuer_present", adjustment=0.05))
    if h.description:
        factors.append(ConfidenceFactor(factor="description_present", adjustment=0.05))
    if any(getattr(h, f) is not None for f in ("fair_value", "cost", "amortized_cost", "principal_amount")):
        factors.append(ConfidenceFactor(factor="monetary_value_present", adjustment=0.10))
    if any(e.source == "parsed_composite_text" for e in lineage.values()):
        factors.append(ConfidenceFactor(factor="composite_parser_match", adjustment=0.05))
    if h.field_conflicts:
        factors.append(ConfidenceFactor(factor="conflicting_facts", adjustment=-0.20, note=",".join(sorted({c.field for c in h.field_conflicts}))))
    if match_status == "ambiguous":
        factors.append(ConfidenceFactor(factor="ambiguous_html_match", adjustment=-0.15))
    if any(e.source == "reviewed_override" for e in lineage.values()):
        factors.append(ConfidenceFactor(factor="reviewed_override_applied", adjustment=0.0, note="no automatic increase"))
    score = max(0.0, min(1.0, sum(f.adjustment for f in factors)))
    if h.source_method == "html_only":
        if score > HTML_ONLY_CAP:
            factors.append(ConfidenceFactor(factor="unmatched_html_only_cap", adjustment=round(HTML_ONLY_CAP - score, 4)))
            score = HTML_ONLY_CAP
    h.confidence_factors = factors
    h.extraction_confidence = round(score, 4)
    return h.extraction_confidence
