from datetime import date

import pytest

from bdc_soi.axis_discovery import score_axes, select_holding_axis
from bdc_soi.models import FactRecord
from bdc_soi.role_discovery import discover_roles
from bdc_soi.templates import RowAxesSpec
from bdc_soi.xbrl_loader import load_model
from tests.conftest import ROOT, SYN


def _fact(i, axis, member, mapped=None):
    return FactRecord(fact_id=f"f{i}", concept_clark="{x}C", concept_prefixed="x:C", local_name="C", namespace="x", context_id=f"c{i}", period_type="instant", period_end=date(2025, 6, 30), dimensions={axis: member}, dimension_labels={axis: member}, dimension_signature=f"{axis}={member}", mapped_field=mapped, order_index=i)


def test_axis_scoring_prefers_identifier_over_classification():
    facts = []
    for i in range(30):
        facts.append(_fact(i, "{x}InvestmentIdentifierAxis", f"typed:holding {i}", "fair_value"))
        facts.append(_fact(100 + i, "{x}FairValueByFairValueHierarchyLevelAxis", "{x}Level3Member", "fair_value"))
        facts.append(_fact(200 + i, "{x}IndustryAxis", f"{{x}}Ind{i % 4}Member", "fair_value"))
    meta = {"{x}InvestmentIdentifierAxis": {"typed": True, "label": "Investment Identifier [Axis]"}, "{x}FairValueByFairValueHierarchyLevelAxis": {"typed": False, "label": "FV Hierarchy"}, "{x}IndustryAxis": {"typed": False, "label": "Industry"}}
    scores = score_axes(facts, date(2025, 6, 30), meta, set(), RowAxesSpec(), {})
    best, reason = select_holding_axis(scores)
    assert best.axis == "{x}InvestmentIdentifierAxis" and reason == "heuristic_best_score"
    by = {s.axis: s for s in scores}
    assert by["{x}FairValueByFairValueHierarchyLevelAxis"].negative_hits and by["{x}IndustryAxis"].negative_hits
    assert by["{x}InvestmentIdentifierAxis"].member_count == 30 and by["{x}InvestmentIdentifierAxis"].positive_hits


def test_template_explicit_axis_overrides_heuristics():
    facts = [_fact(i, "{x}InvestmentIdentifierAxis", f"typed:h{i}", "fair_value") for i in range(10)] + [_fact(50 + i, "{x}LoanAxis", f"{{x}}L{i}", "cost") for i in range(3)]
    meta = {"{x}InvestmentIdentifierAxis": {"typed": True, "label": "id"}, "{x}LoanAxis": {"typed": False, "label": "Loan"}}
    scores = score_axes(facts, date(2025, 6, 30), meta, set(), RowAxesSpec(explicit_qnames=["{x}LoanAxis"]), {})
    best, reason = select_holding_axis(scores)
    assert best.axis == "{x}LoanAxis" and reason == "template_explicit_axis"
    scores = score_axes(facts, date(2025, 6, 30), meta, set(), RowAxesSpec(exclude_regex=["InvestmentIdentifier"]), {})
    best, _ = select_holding_axis(scores)
    assert best is None or best.axis != "{x}InvestmentIdentifierAxis"


def test_tie_is_ambiguous():
    facts = [_fact(i, "{x}AAxis", f"typed:{i}", "fair_value") for i in range(5)] + [_fact(10 + i, "{x}BAxis", f"typed:{i}", "fair_value") for i in range(5)]
    meta = {"{x}AAxis": {"typed": True, "label": "a"}, "{x}BAxis": {"typed": True, "label": "b"}}
    best, reason = select_holding_axis(score_axes(facts, date(2025, 6, 30), meta, set(), None, {}))
    assert best is None and reason.startswith("ambiguous_axis_tie")


def test_role_discovery_on_synthetic_instance():
    loaded = load_model(SYN / "package" / "syn-20250630_htm.xml", ROOT / "cache")
    try:
        rd = discover_roles(loaded.model, [])
    finally:
        loaded.close()
    cands = [r for r in rd.roles if r.is_candidate]
    assert len(cands) == 1 and "Schedule of Investments" in cands[0].definition
    assert "{http://fasb.org/us-gaap/2024}InvestmentOwnedAtFairValue" in rd.soi_concepts
    assert "{http://fasb.org/us-gaap/2024}InvestmentIdentifierAxis" in rd.soi_axes
    assert "{http://fasb.org/us-gaap/2024}FairValueByFairValueHierarchyLevelAxis" not in rd.soi_axes
