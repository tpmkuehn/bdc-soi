from datetime import date

from bdc_soi.config import ValidationConfig
from bdc_soi.confidence import compute_confidence
from bdc_soi.identity import assign_ids, deduplicate, holding_id
from bdc_soi.models import Holding
from bdc_soi.validation import assign_reconciliation_scope, apply_row_rules, reconcile_field


def test_deterministic_holding_id():
    a = holding_id("1837532", "0001193125-26-341358", member_key="typed:Issuer A Term Loan")
    b = holding_id("1837532", "0001193125-26-341358", member_key="typed:Issuer A Term Loan")
    c = holding_id("1837532", "0001193125-26-341358", member_key="typed:Issuer A Revolver")
    d = holding_id("1837532", "0001193125-26-341358", table_row="table_10:t10r5")
    assert a == b and a != c and a != d and len(a) == 32
    assert holding_id("1", "0000000001-25-000001", member_key="x") != holding_id("2", "0000000001-25-000001", member_key="x")


def test_dedup_keeps_distinct_facilities():
    base = dict(cik="1", accession_number="0000000001-25-000001", issuer="Acme", fair_value=100.0, principal_amount=100.0, maturity_date=date(2030, 1, 1))
    h1 = Holding(holding_member_key="typed:Acme TL", description="Term Loan", spread_bps=450, **base)
    h2 = Holding(holding_member_key="typed:Acme RC", description="Revolver", spread_bps=450, **base)
    h3 = Holding(holding_member_key="typed:Acme TL2", description="Term Loan", spread_bps=450, **base)
    assign_ids([h1, h2, h3])
    dd = deduplicate([h1, h2, h3])
    assert len(dd.kept) == 3 and not dd.removed
    assert "possible_duplicate_strong_fields" in h1.review_flags and "possible_duplicate_strong_fields" in h3.review_flags
    assert "possible_duplicate_strong_fields" not in h2.review_flags


def test_reconciliation_statuses():
    cfg = ValidationConfig(total_relative_tolerance=0.005, total_absolute_tolerance=1.0)
    hs = [Holding(cik="1", accession_number="0000000001-25-000001", fair_value=v, reporting_currency="USD") for v in (10.0, 20.0, 30.0)]
    cands = [{"field": "fair_value", "value": 60.0, "source": "xbrl_no_dimensions", "rank": 1, "unit": "USD", "fact_id": "t"}]
    assert reconcile_field("fair_value", hs, cands, cfg, "USD").status == "pass"
    cands[0]["value"] = 70.0
    r = reconcile_field("fair_value", hs, cands, cfg, "USD")
    assert r.status == "fail" and r.difference == -10.0
    assert reconcile_field("fair_value", hs, [], cfg, "USD").status == "not_tested"
    assert reconcile_field("cost", hs, cands, cfg, "USD").status == "no_holdings"
    amb = [{"field": "fair_value", "value": 60.0, "source": "xbrl_no_dimensions", "rank": 1, "unit": "USD", "fact_id": "a"}, {"field": "fair_value", "value": 80.0, "source": "xbrl_no_dimensions", "rank": 1, "unit": "USD", "fact_id": "b"}]
    assert reconcile_field("fair_value", hs, amb, cfg, "USD").status == "ambiguous_total"
    eur = [{"field": "fair_value", "value": 60.0, "source": "xbrl_no_dimensions", "rank": 1, "unit": "EUR", "fact_id": "a"}]
    assert reconcile_field("fair_value", hs, eur, cfg, "USD").status == "not_tested"
    sub = [{"field": "fair_value", "value": 60.0, "source": "html_subtotal", "rank": 5, "fact_id": None, "row_id": "r"}]
    assert reconcile_field("fair_value", hs, sub, cfg, "USD").status == "review"


def test_total_candidate_ranks_follow_spec_16_1():
    cfg = ValidationConfig()
    hs = [Holding(cik="1", accession_number="0000000001-25-000001", fair_value=60.0, reporting_currency="USD")]
    cands = [
        {"field": "fair_value", "value": 61.0, "source": "html_generic_total", "rank": 3, "row_id": "r1"},
        {"field": "fair_value", "value": 60.0, "source": "xbrl_no_dimensions", "rank": 1, "unit": "USD", "fact_id": "f"},
        {"field": "fair_value", "value": 62.0, "source": "html_generic_total", "rank": 3, "row_id": "r2"},
    ]
    r = reconcile_field("fair_value", hs, cands, cfg, "USD")
    assert r.status == "pass" and r.selected_source == "xbrl_no_dimensions" and len(r.candidates) == 3 and r.to_row('1', 'a')['candidate_count'] == 3


def test_row_rules_and_confidence():
    cfg = ValidationConfig()
    h = Holding(cik="1", accession_number="0000000001-25-000001", holding_id="x", fair_value=-5.0, spread=0.5, rate_floor=1.5, issue_date=date(2031, 1, 1), maturity_date=date(2030, 1, 1), currency="GBP", reporting_currency="GBP")
    compute_confidence(h, configured_axis=False, match_status=None)
    apply_row_rules([h], cfg)
    for flag in ("no_issuer_and_no_description", "negative_fair_value", "maturity_before_issue_date", "spread_out_of_bounds", "probable_unit_error:rate_floor", "unexpected_currency:GBP", "low_confidence"):
        assert flag in h.review_flags
    good = Holding(cik="1", accession_number="0000000001-25-000001", holding_id="y", issuer="A", description="B", fair_value=1.0, holding_member_key="k", source_method="html_only")
    good.set_field("fair_value", 1.0, source="html_cell")
    score = compute_confidence(good, configured_axis=True, match_status=None)
    assert score <= 0.60 and any(f.factor == "member_from_configured_holding_axis" for f in good.confidence_factors)


def test_after_total_rows_excluded_from_reconciliation_with_note():
    cfg = ValidationConfig()
    hs = [Holding(cik="1", accession_number="0000000001-25-000001", fair_value=50.0, reporting_currency="USD"), Holding(cik="1", accession_number="0000000001-25-000001", issuer="Dreyfus Treasury Obligations Money Market Fund", fair_value=10.0, reporting_currency="USD", source_method="html_only", review_flags=["unmatched_html_row", "html_row_after_total"])]
    cands = [{"field": "fair_value", "value": 50.0, "source": "xbrl_no_dimensions", "rank": 1, "unit": "USD", "fact_id": "t"}]
    assign_reconciliation_scope(hs)
    r = reconcile_field("fair_value", hs, cands, cfg, "USD")
    assert r.status == "pass" and r.detail_sum == 50.0 and any("after the grand-total row" in n for n in r.notes) and r.bridge.after_total_sum == 10.0
    assert hs[1].reconciliation_scope == "cash_equivalent_after_total" and r.bridge.complete_status == "fail"


def test_template_allows_negative_fair_value_only_with_evidence():
    from bdc_soi.templates import TemplateVersion, validate_template_version

    issues: list[str] = []
    tv = TemplateVersion(id="t", effective_from="2025-01-01", validation={"allow_negative_fair_value": True})
    validate_template_version(tv, "t", issues)
    assert any("evidence" in i for i in issues)
    h = Holding(cik="1", accession_number="0000000001-25-000001", holding_id="x", issuer="A", description="B", fair_value=-5.0)
    apply_row_rules([h], ValidationConfig(), allow_negative_fair_value=True)
    assert "negative_fair_value" not in h.review_flags


def test_total_source_preference_reranks_candidates():
    cfg = ValidationConfig()
    hs = [Holding(cik="1", accession_number="0000000001-25-000001", fair_value=100.0, reporting_currency="USD")]
    cands = [{"field": "fair_value", "value": 137.0, "source": "xbrl_no_dimensions", "rank": 1, "unit": "USD", "fact_id": "f"}, {"field": "fair_value", "value": 100.0, "source": "html_template_total", "rank": 2, "row_id": "r"}]
    assert reconcile_field("fair_value", hs, cands, cfg, "USD").status == "fail"
    r = reconcile_field("fair_value", hs, cands, cfg, "USD", source_preference=["html_template_total"])
    assert r.status == "pass" and r.selected_source == "html_template_total"


def test_subsidiary_dimension_alone_does_not_exclude_rows_from_reconciliation():
    # D47: a subsidiary/legal-entity dimension is flagged but is not exclusion evidence on its own.
    cfg = ValidationConfig()
    hs = [Holding(cik="1", accession_number="0000000001-25-000001", fair_value=50.0, reporting_currency="USD"), Holding(cik="1", accession_number="0000000001-25-000001", fair_value=33.0, reporting_currency="USD", review_flags=["xbrl_subsidiary_context:ConsolidatedSubsidiaryAxis"])]
    cands = [{"field": "fair_value", "value": 50.0, "source": "xbrl_no_dimensions", "rank": 1, "unit": "USD", "fact_id": "t"}]
    assign_reconciliation_scope(hs)
    r = reconcile_field("fair_value", hs, cands, cfg, "USD")
    assert r.status == "fail" and r.bridge.in_scope_sum == 83.0 and hs[1].reconciliation_scope == "schedule"
    assert hs[1].scope_rule == "D47:subsidiary_dimension_in_scope_by_default" and "ConsolidatedSubsidiaryAxis" in hs[1].scope_evidence


def test_dominant_currency_ignores_rows_without_fair_value():
    from bdc_soi.validation import dominant_currency

    hs = [Holding(cik="1", accession_number="0000000001-25-000001", fair_value=10.0, reporting_currency="USD", currency="EUR"), Holding(cik="1", accession_number="0000000001-25-000001", fair_value=None, currency="CHF")]
    assert dominant_currency(hs) == ("USD", False)


def test_matched_rows_reconciling_never_implies_full_output_reconciles():
    cfg = ValidationConfig()
    hs = [Holding(cik="1", accession_number="0000000001-25-000001", fair_value=100.0, reporting_currency="USD", source_method="hybrid_xbrl_html"), Holding(cik="1", accession_number="0000000001-25-000001", fair_value=40.0, reporting_currency="USD", source_method="xbrl")]
    cands = [{"field": "fair_value", "value": 100.0, "source": "xbrl_no_dimensions", "rank": 1, "unit": "USD", "fact_id": "t"}]
    r = reconcile_field("fair_value", hs, cands, cfg, "USD")
    assert r.status == "fail" and r.bridge.matched_only_status == "pass" and r.bridge.xbrl_only_sum == 40.0


def test_full_output_reconciliation_bridge_uses_all_exported_holdings():
    cfg = ValidationConfig()
    base = dict(cik="1", accession_number="0000000001-25-000001", reporting_currency="USD")
    hs = [Holding(fair_value=100.0, source_method="hybrid_xbrl_html", **base), Holding(fair_value=40.0, source_method="xbrl", **base),
          Holding(fair_value=5.0, source_method="html_only", review_flags=["unmatched_html_row"], **base),
          Holding(fair_value=7.0, issuer="Goldman Sachs Financial Square Government Fund", source_method="html_only", review_flags=["unmatched_html_row", "html_row_after_total"], **base)]
    cands = [{"field": "fair_value", "value": 100.0, "source": "xbrl_no_dimensions", "rank": 1, "unit": "USD", "fact_id": "t", "context_id": "c0"}]
    assign_reconciliation_scope(hs)
    r = reconcile_field("fair_value", hs, cands, cfg, "USD", report_date="2025-06-30")
    assert r.status == "fail" and r.detail_sum == 145.0  # complete in-scope output, not matched-only
    b = r.bridge
    assert (b.matched_sum, b.xbrl_only_sum, b.html_only_sum, b.after_total_sum, b.complete_sum, b.in_scope_sum) == (100.0, 40.0, 5.0, 7.0, 152.0, 145.0)
    assert b.matched_only_status == "pass" and any("diagnostic: matched-rows-only" in n for n in r.notes)
    assert r.selected_location.startswith("xbrl fact t") and r.report_date == "2025-06-30"
    row = r.to_row("1", "a")
    assert row["complete_exported_sum"] == 152.0 and row["matched_only_status"] == "pass"
