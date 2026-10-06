"""Holding-axis discovery and scoring (SPEC 11.5)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from bdc_soi.concept_mapping import extract_qname_parts
from bdc_soi.models import FactRecord
from bdc_soi.templates import RowAxesSpec, parse_concept_ref

POSITIVE_INDICATORS = [
    r"InvestmentIdentifier",
    r"Investment.*Identifier",
    r"PortfolioCompany",
    r"Issuer(?!Affiliation)",
    r"Borrower",
    r"Security",
    r"Instrument",
    r"LoanIdentifier",
    r"InvestmentName",
    r"Holding",
]
NEGATIVE_INDICATORS = [
    r"FairValue.*Hierarchy",
    r"FairValueByFairValueHierarchyLevel",
    r"Level[123]",
    r"Industry",
    r"Sector",
    r"Geograph",
    r"Country",
    r"Region",
    r"Affiliat",
    r"Control",
    r"Currency",
    r"InvestmentType",
    r"TypeOfInvestment",
    r"ClassOfStock",
    r"StatementClassOfStock",
    r"Consolidat",
    r"Segment",
    r"Range",
    r"MeasurementInput",
    r"ValuationTechnique",
    r"DebtInstrument",
    r"LineOfCredit",
    r"Subsequent",
    r"Related",
    r"Concentration",
    r"Award",
    r"Plan",
    r"Equity",
    r"IncomeStatement",
    r"BusinessAcquisition",
]
MONETARY_HOLDING_FIELDS = {"fair_value", "cost", "amortized_cost", "principal_amount", "face_amount", "shares"}


@dataclass
class AxisScore:
    axis: str
    label: str
    typed: bool
    member_count: int
    fact_count: int
    context_count: int
    mapped_fraction: float
    in_soi_role: bool
    positive_hits: list[str] = field(default_factory=list)
    negative_hits: list[str] = field(default_factory=list)
    template_match: str | None = None
    excluded_by_template: bool = False
    example_members: list[str] = field(default_factory=list)
    score: float = 0.0
    selected: bool = False
    reason: str = ""

    def to_row(self) -> dict[str, Any]:
        import json

        d = self.__dict__.copy()
        d["positive_hits"] = json.dumps(self.positive_hits)
        d["negative_hits"] = json.dumps(self.negative_hits)
        d["example_members"] = json.dumps(self.example_members)
        return d


def score_axes(
    facts: list[FactRecord],
    report_date: date | None,
    axes_meta: dict[str, dict[str, Any]],
    soi_axes: set[str],
    row_axes: RowAxesSpec | None,
    families: dict[str, re.Pattern[str]],
    min_members: int = 3,
) -> list[AxisScore]:
    at_date = [f for f in facts if report_date is None or f.period_end == report_date]
    per_axis: dict[str, dict[str, Any]] = {}
    for f in at_date:
        for axis, member in f.dimensions.items():
            info = per_axis.setdefault(axis, {"members": set(), "facts": 0, "contexts": set(), "mapped": 0, "labels": {}})
            info["members"].add(member)
            info["facts"] += 1
            info["contexts"].add(f.context_id)
            if f.mapped_field in MONETARY_HOLDING_FIELDS:
                info["mapped"] += 1
            info["labels"].setdefault(member, f.dimension_labels.get(axis, member))
    explicit = [parse_concept_ref(q) for q in (row_axes.explicit_qnames if row_axes else [])]
    inc_regex = [re.compile(p, re.IGNORECASE) for p in (row_axes.regex if row_axes else [])]
    exc_regex = [re.compile(p, re.IGNORECASE) for p in (row_axes.exclude_regex if row_axes else [])]
    pos = [re.compile(p, re.IGNORECASE) for p in POSITIVE_INDICATORS]
    neg = [re.compile(p, re.IGNORECASE) for p in NEGATIVE_INDICATORS]

    scores: list[AxisScore] = []
    for axis in sorted(per_axis):
        info = per_axis[axis]
        ns, local = extract_qname_parts(axis)
        meta = axes_meta.get(axis, {})
        s = AxisScore(
            axis=axis,
            label=str(meta.get("label") or local),
            typed=bool(meta.get("typed", False)),
            member_count=len(info["members"]),
            fact_count=info["facts"],
            context_count=len(info["contexts"]),
            mapped_fraction=(info["mapped"] / info["facts"]) if info["facts"] else 0.0,
            in_soi_role=axis in soi_axes,
            example_members=[str(info["labels"][m])[:160] for m in sorted(info["members"])[:5]],
        )
        s.positive_hits = [p.pattern for p in pos if p.search(local)]
        s.negative_hits = [p.pattern for p in neg if p.search(local)]
        for cref in explicit:
            if cref.matches(axis, ns, local, families):
                s.template_match = f"explicit:{cref.raw}"
        if not s.template_match:
            for pat in inc_regex:
                if pat.search(local) or pat.search(s.label):
                    s.template_match = f"regex:{pat.pattern}"
                    break
        for pat in exc_regex:
            if pat.search(local) or pat.search(s.label):
                s.excluded_by_template = True
        score = 0.0
        score += 3.0 * min(1.0, s.member_count / 25.0)
        score += 2.0 * s.mapped_fraction
        score += 1.0 if s.in_soi_role else 0.0
        score += 2.0 if s.positive_hits else 0.0
        score += 1.0 if s.typed else 0.0
        score -= 3.0 if s.negative_hits else 0.0
        if s.member_count < min_members:
            score -= 2.0
        if s.template_match and s.template_match.startswith("explicit:"):
            score += 100.0
        elif s.template_match:
            score += 10.0
        if s.excluded_by_template:
            score -= 100.0
        s.score = round(score, 4)
        scores.append(s)
    return scores


def select_holding_axis(scores: list[AxisScore], minimum_score: float = 2.0) -> tuple[AxisScore | None, str]:
    """Pick the best-scoring axis deterministically; template-specified axes override heuristics."""
    if not scores:
        return None, "no_dimensional_facts_at_report_date"
    explicit = [s for s in scores if s.template_match and s.template_match.startswith("explicit:") and not s.excluded_by_template]
    if explicit:
        best = sorted(explicit, key=lambda s: (-s.score, s.axis))[0]
        best.selected = True
        best.reason = "template_explicit_axis"
        return best, best.reason
    ranked = sorted((s for s in scores if not s.excluded_by_template), key=lambda s: (-s.score, s.axis))
    if not ranked:
        return None, "all_axes_excluded_by_template"
    best = ranked[0]
    if best.score < minimum_score:
        return None, f"best_axis_below_threshold:{best.axis}:{best.score}"
    if len(ranked) > 1 and ranked[1].score == best.score:
        return None, f"ambiguous_axis_tie:{best.axis}|{ranked[1].axis}"
    best.selected = True
    best.reason = "template_regex_axis" if best.template_match else "heuristic_best_score"
    return best, best.reason
