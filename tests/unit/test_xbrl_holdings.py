import re
from datetime import date

from bdc_soi.concept_mapping import ConceptMapper
from bdc_soi.models import FactRecord
from bdc_soi.templates import XbrlSpec
from bdc_soi.xbrl_holdings import build_xbrl_holdings, rank_fact

FAM = {"us-gaap": re.compile(r"^http://fasb\.org/us-gaap/\d{4}$")}
AX = "{http://fasb.org/us-gaap/2024}InvestmentIdentifierAxis"
BASE = dict(cik="1", company_name="T", accession_number="0000000001-25-000001", report_date=date(2025, 6, 30), engine_version="t")


def _fact(fid, concept, value, dims, unit="USD", decimals="-3", nil=False, in_role=True, mapped="fair_value", rule="generic_exact:us-gaap:X", order=0):
    ns, local = concept[1:].split("}")
    return FactRecord(fact_id=fid, concept_clark=concept, concept_prefixed=local, local_name=local, namespace=ns, raw_value=None if nil else str(value), numeric_value=None if nil else float(value), is_nil=nil, unit=unit, decimals=decimals, context_id=f"c_{fid}", period_type="instant", period_end=date(2025, 6, 30), dimensions=dims, dimension_labels={k: v for k, v in dims.items()}, dimension_signature="|".join(f"{k}={v}" for k, v in sorted(dims.items())), in_soi_role=in_role, mapped_field=mapped, mapping_rule=rule, order_index=order)


def _generic():
    return XbrlSpec(field_concepts={"fair_value": ["us-gaap:InvestmentOwnedAtFairValue"], "cost": ["us-gaap:InvestmentOwnedAtCost"]})


def test_duplicate_fact_selection_prefers_role_nonnil_fewer_dims_and_records_conflict():
    fv = "{http://fasb.org/us-gaap/2024}InvestmentOwnedAtFairValue"
    member = "typed:Issuer A Investment Type Term Loan"
    facts = [
        _fact("nil", fv, 0, {AX: member}, nil=True, order=0),
        _fact("extra_dim", fv, 1001000, {AX: member, "{x}FVHierarchyAxis": "{x}L3"}, in_role=False, order=1),
        _fact("best", fv, 1000000, {AX: member}, order=2),
        _fact("other_cost", "{http://fasb.org/us-gaap/2024}InvestmentOwnedAtCost", 990000, {AX: member}, mapped="cost", order=3),
    ]
    mapper = ConceptMapper.build(None, _generic(), FAM, [])
    xe = build_xbrl_holdings(facts, date(2025, 6, 30), AX, mapper, None, _generic(), FAM, BASE)
    assert len(xe.holdings) == 1
    h = xe.holdings[0]
    assert h.fair_value == 1000000.0 and h.field_lineage["fair_value"].source_ref == "best"
    assert h.cost == 990000.0
    assert any(c.field == "fair_value" for c in h.field_conflicts) and "field_conflict:fair_value" in h.review_flags
    conflict = next(c for c in h.field_conflicts if c.field == "fair_value")
    assert conflict.alternatives[0]["fact_id"] == "extra_dim"
    assert "{x}FVHierarchyAxis" in h.dimension_signature  # classification dims preserved as lineage
    assert h.issuer_name_raw == "Issuer A Investment Type Term Loan"


def test_repeated_issuer_facilities_stay_separate():
    fv = "{http://fasb.org/us-gaap/2024}InvestmentOwnedAtFairValue"
    facts = [
        _fact("a", fv, 5000, {AX: "typed:Alpine Health Term Loan"}, order=0),
        _fact("b", fv, 5000, {AX: "typed:Alpine Health Revolver"}, order=1),
    ]
    mapper = ConceptMapper.build(None, _generic(), FAM, [])
    xe = build_xbrl_holdings(facts, date(2025, 6, 30), AX, mapper, None, _generic(), FAM, BASE)
    assert len(xe.holdings) == 2 and {h.holding_member_key for h in xe.holdings} == {"typed:Alpine Health Term Loan", "typed:Alpine Health Revolver"}


def test_totals_without_holding_axis_are_candidates():
    fv = "{http://fasb.org/us-gaap/2024}InvestmentOwnedAtFairValue"
    facts = [
        _fact("h", fv, 100, {AX: "typed:x"}),
        _fact("total", fv, 100, {}),
        _fact("sub", fv, 100, {"{x}IndustryAxis": "{x}Software"}),
        _fact("prior", fv, 90, {}),
    ]
    facts[-1].period_end = date(2024, 12, 31)
    mapper = ConceptMapper.build(None, _generic(), FAM, [])
    xe = build_xbrl_holdings(facts, date(2025, 6, 30), AX, mapper, None, _generic(), FAM, BASE)
    sources = {t.fact_id: t.source for t in xe.totals}
    assert sources == {"total": "xbrl_no_dimensions", "sub": "xbrl_classification_subtotal"}


def test_classification_dimension_becomes_field_not_holding():
    fv = "{http://fasb.org/us-gaap/2024}InvestmentOwnedAtFairValue"
    facts = [_fact("a", fv, 1, {AX: "typed:Issuer", "{x}EquitySecuritiesByIndustryAxis": "{x}SoftwareMember"})]
    facts[0].dimension_labels["{x}EquitySecuritiesByIndustryAxis"] = "Software [Member]"
    mapper = ConceptMapper.build(None, _generic(), FAM, [])
    xe = build_xbrl_holdings(facts, date(2025, 6, 30), AX, mapper, None, _generic(), FAM, BASE)
    h = xe.holdings[0]
    assert h.industry == "Software" and h.field_lineage["industry"].source == "xbrl_dimension_member"


def test_issuer_name_axis_member_is_direct_issuer_source():
    # Observed in Apollo Debt Solutions 10-Q (2026-06-30): us-gaap:InvestmentIssuerNameAxis members carry issuer names.
    fv = "{http://fasb.org/us-gaap/2024}InvestmentOwnedAtFairValue"
    facts = [_fact("a", fv, 1, {AX: "typed:Software Acme Holdings, LLC Investment Type Term Loan", "{http://fasb.org/us-gaap/2024}InvestmentIssuerNameAxis": "{x}AcmeHoldingsLlcMember"})]
    facts[0].dimension_labels["{http://fasb.org/us-gaap/2024}InvestmentIssuerNameAxis"] = "Acme Holdings, LLC [Member]"
    mapper = ConceptMapper.build(None, _generic(), FAM, [])
    xe = build_xbrl_holdings(facts, date(2025, 6, 30), AX, mapper, None, _generic(), FAM, BASE)
    h = xe.holdings[0]
    assert h.issuer == "Acme Holdings LLC" and h.field_lineage["issuer"].source == "xbrl_dimension_member"
    assert h.issuer_name_raw == "Acme Holdings, LLC" and h.field_lineage["issuer"].raw_value == "Acme Holdings, LLC [Member]"


def test_reference_index_extensible_enumeration_normalized():
    enum = "{http://fasb.org/us-gaap/2024}InvestmentVariableInterestRateTypeExtensibleEnumeration"
    f = _fact("r", enum, 0, {AX: "typed:x"}, unit=None, decimals=None, mapped="reference_index")
    f.raw_value = "http://fasb.org/us-gaap/2025#SecuredOvernightFinancingRateSofrMember"
    f.numeric_value = None
    gen = XbrlSpec(field_concepts={"reference_index": ["us-gaap:InvestmentVariableInterestRateTypeExtensibleEnumeration"], "fair_value": ["us-gaap:InvestmentOwnedAtFairValue"]})
    mapper = ConceptMapper.build(None, gen, FAM, [])
    fv = _fact("fv", "{http://fasb.org/us-gaap/2024}InvestmentOwnedAtFairValue", 10, {AX: "typed:x"})
    xe = build_xbrl_holdings([f, fv], date(2025, 6, 30), AX, mapper, None, gen, FAM, BASE)
    assert xe.holdings[0].reference_index == "SOFR"


def test_currency_from_principal_unit_and_reporting_currency():
    fv = "{http://fasb.org/us-gaap/2024}InvestmentOwnedAtFairValue"
    pr = "{http://fasb.org/us-gaap/2024}InvestmentOwnedBalancePrincipalAmount"
    facts = [_fact("f", fv, 100, {AX: "typed:x"}, unit="USD"), _fact("p", pr, 90, {AX: "typed:x"}, unit="EUR", mapped="principal_amount")]
    gen = XbrlSpec(field_concepts={"fair_value": ["us-gaap:InvestmentOwnedAtFairValue"], "principal_amount": ["us-gaap:InvestmentOwnedBalancePrincipalAmount"]})
    mapper = ConceptMapper.build(None, gen, FAM, [])
    h = build_xbrl_holdings(facts, date(2025, 6, 30), AX, mapper, None, gen, FAM, BASE).holdings[0]
    assert h.currency == "EUR" and h.reporting_currency == "USD" and "mixed_currencies_in_holding" not in h.review_flags


def test_template_total_concept_matches_only_undimensioned_facts():
    # Apollo run 1: every us-gaap:InvestmentOwnedAtFairValue subtotal became a rank-0 template total -> ambiguous.
    fv = "{http://fasb.org/us-gaap/2024}InvestmentOwnedAtFairValue"
    facts = [_fact("h", fv, 100, {AX: "typed:x"}), _fact("total", fv, 100, {}), _fact("sub", fv, 60, {"{x}IndustryAxis": "{x}Software"})]
    spec = XbrlSpec(total_concepts={"fair_value": ["us-gaap:InvestmentOwnedAtFairValue"]})
    mapper = ConceptMapper.build(spec, _generic(), FAM, [])
    xe = build_xbrl_holdings(facts, date(2025, 6, 30), AX, mapper, spec, _generic(), FAM, BASE)
    ranks = {t.fact_id: (t.source, t.rank) for t in xe.totals}
    assert ranks["total"] == ("xbrl_template_total", 0) and ranks["sub"] == ("xbrl_classification_subtotal", 4)


def test_groups_without_monetary_values_are_not_holdings():
    sp = "{http://fasb.org/us-gaap/2024}InvestmentBasisSpreadVariableRate"
    fv = "{http://fasb.org/us-gaap/2024}InvestmentOwnedAtFairValue"
    facts = [_fact("s", sp, 0.045, {AX: "typed:Investment 80/20 commitment"}, unit="pure", decimals="4", mapped="spread"), _fact("f", fv, 100, {AX: "typed:Real holding"})]
    gen = XbrlSpec(field_concepts={"fair_value": ["us-gaap:InvestmentOwnedAtFairValue"], "spread": ["us-gaap:InvestmentBasisSpreadVariableRate"]})
    mapper = ConceptMapper.build(None, gen, FAM, [])
    xe = build_xbrl_holdings(facts, date(2025, 6, 30), AX, mapper, None, gen, FAM, BASE)
    assert [h.holding_member_key for h in xe.holdings] == ["typed:Real holding"] and xe.group_count == 2
    assert any(n.startswith("xbrl_groups_without_monetary_values_excluded:1") for n in xe.notes)


def test_parent_section_members_are_excluded_when_children_sum():
    # Investcorp: 'Investment in non-controlled, Affiliated Investment' (9,514,365) is the sum of its labelled children.
    fv = "{http://fasb.org/us-gaap/2024}InvestmentOwnedAtFairValue"
    facts = [
        _fact("p", fv, 30, {AX: "typed:Investment in non-controlled, Affiliated Investments"}, order=0),
        _fact("c1", fv, 10, {AX: "typed:Investment in non-controlled, Affiliated Investments, Acme LLC, Class A Units"}, order=1),
        _fact("c2", fv, 20, {AX: "typed:Investment in non-controlled, Affiliated Investments, Acme LLC, Term Loan"}, order=2),
        _fact("x", fv, 5, {AX: "typed:Beta Corp | Term Loan"}, order=3),
        _fact("y", fv, 7, {AX: "typed:Beta Corp | Term Loan 2"}, order=4),  # prefix but values do not sum -> both kept
    ]
    mapper = ConceptMapper.build(None, _generic(), FAM, [])
    xe = build_xbrl_holdings(facts, date(2025, 6, 30), AX, mapper, None, _generic(), FAM, BASE)
    keys = {h.holding_member_key for h in xe.holdings}
    assert "typed:Investment in non-controlled, Affiliated Investments" not in keys and len(keys) == 4
    assert any(n.startswith("xbrl_parent_member_excluded") for n in xe.notes)


def test_total_and_net_asset_members_are_not_holdings_but_total_candidates():
    # PIMCO: a typed member 'Total Investments' doubled the detail sum; Muzinich: 'Net Assets' members.
    fv = "{http://fasb.org/us-gaap/2024}InvestmentOwnedAtFairValue"
    facts = [_fact("a", fv, 60, {AX: "typed:Acme | Term Loan"}), _fact("t", fv, 60, {AX: "typed:Total Investments"}), _fact("n", fv, 50, {AX: "typed:Net Assets"})]
    mapper = ConceptMapper.build(None, _generic(), FAM, [])
    xe = build_xbrl_holdings(facts, date(2025, 6, 30), AX, mapper, None, _generic(), FAM, BASE)
    assert [h.holding_member_key for h in xe.holdings] == ["typed:Acme | Term Loan"]
    assert any(t.source == "xbrl_member_total" and t.value == 60 and t.rank == 1 for t in xe.totals)


def test_subsidiary_context_holdings_are_flagged():
    fv = "{http://fasb.org/us-gaap/2024}InvestmentOwnedAtFairValue"
    facts = [_fact("a", fv, 10, {AX: "typed:Acme | Loan", "{http://x}ConsolidatedSubsidiaryAxis": "{x}JocasseeMember"})]
    mapper = ConceptMapper.build(None, _generic(), FAM, [])
    xe = build_xbrl_holdings(facts, date(2025, 6, 30), AX, mapper, None, _generic(), FAM, BASE)
    assert any(f.startswith("xbrl_subsidiary_context:ConsolidatedSubsidiaryAxis") for f in xe.holdings[0].review_flags)


def test_single_prefixed_sibling_is_not_a_parent():
    # Barings: 'EMI Porta Holdco LLC | Revolver' and '... | Revolver | Funded' are two facilities, both counted in the total.
    fv = "{http://fasb.org/us-gaap/2024}InvestmentOwnedAtFairValue"
    facts = [_fact("a", fv, 2300, {AX: "typed:EMI Porta Holdco LLC | Revolver"}, order=0), _fact("b", fv, 2300, {AX: "typed:EMI Porta Holdco LLC | Revolver | Funded"}, order=1)]
    mapper = ConceptMapper.build(None, _generic(), FAM, [])
    xe = build_xbrl_holdings(facts, date(2025, 6, 30), AX, mapper, None, _generic(), FAM, BASE)
    assert len(xe.holdings) == 2


def test_template_member_exclusion_with_evidence():
    from bdc_soi.templates import RowAxesSpec

    fv = "{http://fasb.org/us-gaap/2024}InvestmentOwnedAtFairValue"
    facts = [_fact("a", fv, 12879, {AX: "typed:Eclipse | Revolver"}), _fact("b", fv, 12900, {AX: "typed:Eclipse Holdings | Revolver | Funded"})]
    spec = XbrlSpec(row_axes=RowAxesSpec(exclude_member_regex=[r"\| Funded$"], exclude_member_evidence="Barings tags funded portions as separate members"))
    mapper = ConceptMapper.build(spec, _generic(), FAM, [])
    xe = build_xbrl_holdings(facts, date(2025, 6, 30), AX, mapper, spec, _generic(), FAM, BASE)
    assert [h.holding_member_key for h in xe.holdings] == ["typed:Eclipse | Revolver"] and any(n.startswith("xbrl_member_excluded_by_template") for n in xe.notes)


def test_issuer_named_total_is_a_holding_member():
    # TriplePoint: 'Total Expert Inc. | Growth Capital Loan' is an issuer; only exact total phrasings are excluded.
    fv = "{http://fasb.org/us-gaap/2024}InvestmentOwnedAtFairValue"
    facts = [_fact("a", fv, 22121000, {AX: "typed:Total Expert Inc. | Growth Capital Loan"}), _fact("t", fv, 60, {AX: "typed:Total Investments"}), _fact("u", fv, 60, {AX: "typed:Total investments, June 30, 2026"})]
    mapper = ConceptMapper.build(None, _generic(), FAM, [])
    xe = build_xbrl_holdings(facts, date(2025, 6, 30), AX, mapper, None, _generic(), FAM, BASE)
    assert [h.holding_member_key for h in xe.holdings] == ["typed:Total Expert Inc. | Growth Capital Loan"]


def test_affiliate_schedule_members_become_excluded_candidates():
    # Chicago Atlantic prior period: 'CO Acquisition Vehicle LLC' carries roll-forward concepts and a fair value, no SOI facts.
    fv = "{http://fasb.org/us-gaap/2024}InvestmentOwnedAtFairValue"
    add = "{http://fasb.org/us-gaap/2024}InvestmentsInAndAdvancesToAffiliatesAtFairValueGrossAdditions"
    facts = [_fact("a", fv, 17370481, {AX: "typed:CO Acquisition Vehicle LLC"}), _fact("b", add, 16310311, {AX: "typed:CO Acquisition Vehicle LLC"}, mapped=None, rule=None),]
    facts[1].period_type, facts[1].period_start = "duration", date(2025, 1, 1)  # roll-forward facts are duration facts outside the instant filter
    facts += [
             _fact("c", fv, 5, {AX: "typed:Acme | Term Loan"}), _fact("d", "{http://fasb.org/us-gaap/2024}InvestmentOwnedBalancePrincipalAmount", 5, {AX: "typed:Acme | Term Loan"}, mapped="principal_amount")]
    mapper = ConceptMapper.build(None, _generic(), FAM, [])
    xe = build_xbrl_holdings(facts, date(2025, 6, 30), AX, mapper, None, _generic(), FAM, BASE)
    assert [h.holding_member_key for h in xe.holdings] == ["typed:Acme | Term Loan"]
    ex = [e for e in xe.excluded if e.rule == "generic:affiliate_schedule_member"]
    assert len(ex) == 1 and ex[0].fair_value == 17370481 and "GrossAdditions" in ex[0].evidence and ex[0].fact_ids == ["a"]
