

def test_reconciliation_scope_keeps_cash_equivalents_outside_and_subsidiary_sections_inside():
    # Audax 2026-06-30: 'Audax Credit BDC Equity, LLC' rows follow the 'Total Investments' row but are inside the XBRL
    # total; TriplePoint's 'Federated Government Obligations Fund ... Cash Equivalents' row after the total is not.
    from bdc_soi.models import Holding
    from bdc_soi.validation import assign_reconciliation_scope, reconcile_field
    from bdc_soi.config import ValidationConfig

    def mk(hid, issuer, desc, fv, flags=(), row="t1r1", method="html_only"):
        h = Holding(cik="1", accession_number="0000000001-25-000001", holding_id=hid, holding_member_key=hid, issuer=issuer, description=desc, fair_value=fv, source_method=method, source_table=f"table_1:{row}", html_row_id=row)
        for f in flags:
            h.add_flag(f)
        return h

    hs = [mk("a", "Acme", "First Lien", 1000.0, method="hybrid_xbrl_html"),
          mk("b", "Federated Government Obligations Fund", "Cash Equivalents", 500.0, ["html_row_after_total"], "t2r9"),
          mk("c", "Dane Street", "Class A Units", 10.0, ["html_row_after_total"], "t3r2", method="hybrid_xbrl_html"),
          mk("d", "Sub LLC", "Term Loan", 7.0, ["xbrl_subsidiary_context:LegalEntityAxis"], method="xbrl")]
    assign_reconciliation_scope(hs, row_texts={"t2r9": "Federated Government Obligations Fund GOFFX 500 500", "t3r2": "Dane Street Class A Units 10 10"}, section_headings={"t3r2": "Audax Credit BDC Equity, LLC"})
    # D47: a subsidiary dimension alone does not exclude a row; it stays in scope with an explicit default rule.
    assert [h.reconciliation_scope for h in hs] == ["schedule", "cash_equivalent_after_total", "after_total_section", "schedule"]
    assert hs[0].scope_rule == "D43:schedule_default" and hs[3].scope_rule == "D47:subsidiary_dimension_in_scope_by_default"
    assert hs[1].scope_rule == "D43:cash_equivalent_after_total" and "Government" in hs[1].scope_evidence
    assert "after_total_section_in_scope" in hs[2].review_flags and hs[2].scope_evidence.startswith("after grand-total row without")
    hs.append(mk("e", "Acme", "Second Lien", None, row="t1r9"))  # exported row without a fair value: counted in scope_rows_all only
    cands = [{"field": "fair_value", "value": 1017.0, "source": "xbrl_template_total", "rank": 0, "fact_id": "f1", "context_id": "c1", "unit": "USD"}]
    res = reconcile_field("fair_value", hs, cands, ValidationConfig(), "USD")
    assert res.status == "pass" and res.bridge.in_scope_sum == 1017.0 and res.bridge.complete_sum == 1517.0
    assert res.bridge.complete_status == "fail" and res.bridge.after_total_sum == 500.0 and res.bridge.subsidiary_sum == 0.0
    assert res.bridge.scope_rules == {"schedule": 2, "cash_equivalent_after_total": 1, "after_total_section": 1}
    assert res.bridge.scope_rows_all == {"schedule": 3, "cash_equivalent_after_total": 1, "after_total_section": 1} and res.bridge.acceptance == "not_assessed"
    assert any("scoped status pass differs from complete-exported status fail" in n for n in res.notes)


def test_conflict_classes_separate_formatting_from_identity_semantic_and_numeric():
    from bdc_soi.validation import classify_conflict

    assert classify_conflict("issuer", "Acme Holdings LLC", [{"value": "Acme Holdings, L.L.C."}]) == "formatting"
    assert classify_conflict("issuer", "LendingTree Inc", [{"value": "Consumer Finance LendingTree LendingTree Inc"}]) == "formatting"  # label containment
    assert classify_conflict("description", "First Lien 3", [{"value": "First Lien"}]) == "formatting"  # sequence suffix
    assert classify_conflict("issuer", "Integrative Life Network LLC", [{"value": "CareSave Technologies Inc"}]) == "identity"
    assert classify_conflict("description", "Series E-2 Preferred Stock", [{"value": "Class A Common Stock"}]) == "identity"
    assert classify_conflict("affiliate_status", "Non-controlled, non-affiliated", [{"value": "Controlled"}]) == "semantic"
    assert classify_conflict("affiliate_status", "Non-Controlled/Non-Affiliated Investments", [{"value": "non-controlled, non-affiliated"}]) == "formatting"
    assert classify_conflict("fair_value", 100.0, [{"value": 101.0}]) == "numeric"
    assert classify_conflict("maturity_date", "2030-01-01", [{"value": "2030-06-30"}]) == "numeric"


def test_holding_row_export_carries_scope_identity_and_conflict_columns():
    # The final-run CSVs showed blank scope/identity columns: the model held the values but to_row() omitted them.
    from bdc_soi.models import HOLDING_COLUMNS, FieldConflict, Holding

    h = Holding(cik="1", accession_number="0000000001-25-000001", holding_id="x", reconciliation_scope="cash_equivalent_after_total", scope_rule="D43:cash_equivalent_after_total", scope_evidence="e", identity_resolution="group", match_group_id="grp:a:1:1:1", fair_value_unit_original="CAD", reporting_currency="USD", conflict_classes={"formatting": 2})
    row = h.to_row()
    for col in ("reconciliation_scope", "scope_rule", "scope_evidence", "identity_resolution", "match_group_id", "fair_value_unit_original", "conflict_classes"):
        assert col in row and col in HOLDING_COLUMNS, col
    assert row["reconciliation_scope"] == "cash_equivalent_after_total" and row["identity_resolution"] == "group" and row["conflict_classes"] == '{"formatting": 2}'
    assert set(row) == set(HOLDING_COLUMNS)


def test_contradictory_duplicate_is_outside_the_sums_and_blocks_acceptance_regardless_of_tolerance():
    # BIP: the CareSave-labelled XBRL candidate and the Integrative Life HTML row carry the same 142,480; counting both
    # passed tolerance by accident. Identity acceptance is separate from numerical reconciliation.
    from bdc_soi.models import Holding
    from bdc_soi.validation import assign_reconciliation_scope, reconcile_field
    from bdc_soi.config import ValidationConfig

    base = dict(cik="1", accession_number="0000000001-25-000001")
    x = Holding(holding_id="x", issuer="CareSave Technologies Inc", description="Series E-2 Preferred Stock", fair_value=142480.0, source_method="xbrl", **base)
    x.add_flag("contradictory_identity_candidate:t1r5")
    x.reconciliation_scope, x.scope_rule = "contradictory_identity_duplicate", "D46:contradictory_identity_duplicate"
    y = Holding(holding_id="y", issuer="Integrative Life Network LLC", description="Class A Common Stock", fair_value=142480.0, source_method="html_only", html_row_id="t1r5", **base)
    y.add_flag("contradictory_identity_candidate:x")
    z = Holding(holding_id="z", issuer="Acme", description="First Lien", fair_value=1000.0, source_method="hybrid_xbrl_html", **base)
    hs = [x, y, z]
    assign_reconciliation_scope(hs)
    assert x.reconciliation_scope == "contradictory_identity_duplicate" and y.reconciliation_scope == "schedule"
    res = reconcile_field("fair_value", hs, [{"field": "fair_value", "value": 143480.0, "source": "xbrl_template_total", "rank": 0, "fact_id": "f", "context_id": "c", "unit": "USD"}], ValidationConfig(), "USD")
    assert res.status == "pass" and res.bridge.duplicate_candidate_sum == 142480.0 and res.bridge.in_scope_sum == 143480.0
    assert res.bridge.acceptance.startswith("blocked:unresolved_identity_contradiction") and any("ACCEPTANCE blocked" in n for n in res.notes)


def test_contradictory_candidate_is_scoped_as_duplicate_only_with_sibling_member_evidence():
    # BIP: the instance carries 'Integrative Life Network, LLC Type Class A Common Stock Acquisition Date 12/12/2024'
    # as its own identifier member (December facts, June acquisition-date fact); that sibling evidence, not the
    # totals, makes the CareSave-labelled candidate a duplicate. Without a sibling both candidates stay in scope.
    from bdc_soi.html_tables import HtmlRow
    from bdc_soi.models import FactRecord, Holding
    from bdc_soi.pipeline import _scope_contradictory_duplicate

    def fact(label, name, end):
        from datetime import date as _d
        return FactRecord(fact_id="f", concept_clark="{u}" + name, concept_prefixed="us-gaap:" + name, local_name=name, namespace="u", raw_value="1", numeric_value=1.0, unit="USD", context_id="c", period_type="instant", period_end=_d.fromisoformat(end), dimensions={"{u}InvestmentIdentifierAxis": "typed:" + label}, dimension_labels={"{u}InvestmentIdentifierAxis": label}, in_soi_role=True)

    h = Holding(cik="1", accession_number="0000000001-25-000001", holding_id="x", issuer="CareSave Technologies Inc", description="Series E-2 Preferred Stock", fair_value=142480.0, member_labels={"{u}InvestmentIdentifierAxis": "Investments Equity Investments CareSave Technologies, Inc. Type Series E-2 Preferred Stock Acquisition Date 12/12/2024"})
    row = HtmlRow(1, 5, "t1r5", "holding", [], "", fields_raw={}, fields={"issuer": "Integrative Life Network, LLC", "description": "Class A Common Stock", "fair_value": 142480.0})
    facts = [fact("Investments Equity Investments Healthcare Integrative Life Network, LLC Type Class A Common Stock Acquisition Date 12/12/2024", "InvestmentOwnedAtCost", "2025-12-31")]
    _scope_contradictory_duplicate(h, [row], facts, None)
    assert h.reconciliation_scope == "contradictory_identity_duplicate" and h.scope_rule == "D46:contradictory_identity_duplicate"
    assert "Integrative Life Network" in h.scope_evidence and "canonical_candidate_by_source_evidence:t1r5" in h.review_flags
    h2 = Holding(cik="1", accession_number="0000000001-25-000001", holding_id="y", issuer="CareSave Technologies Inc", description="Series E-2 Preferred Stock", fair_value=142480.0)
    _scope_contradictory_duplicate(h2, [row], [], None)
    assert h2.reconciliation_scope == "schedule" and h2.scope_rule is None
    # A sibling that carries its own report-date fair value is a different position (Crescent: RWA Wealth Partners
    # matched to its own member while Hercules' cost coincided): no duplicate scoping.
    from datetime import date as _d
    h3 = Holding(cik="1", accession_number="0000000001-25-000001", holding_id="z", issuer="Hercules Borrower LLC", description="Common Stock", fair_value=2116000.0)
    row2 = HtmlRow(1, 6, "t1r6", "holding", [], "", fields_raw={}, fields={"issuer": "RWA Wealth Partners, LLC.", "description": "Unitranche First Lien Delayed Draw Term Loan", "cost": 1153000.0})
    facts2 = [fact("Investments Diversified Financials RWA Wealth Partners, LLC. Investment Type Unitranche First Lien Delayed Draw Term Loan", "InvestmentOwnedAtFairValue", "2026-06-30")]
    _scope_contradictory_duplicate(h3, [row2], facts2, _d(2026, 6, 30))
    assert h3.reconciliation_scope == "schedule"
