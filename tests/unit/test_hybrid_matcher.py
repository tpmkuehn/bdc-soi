from datetime import date

from bdc_soi.config import MatchingConfig
from bdc_soi.html_tables import HtmlRow
from bdc_soi.hybrid_matcher import match_holdings, score_pair
from bdc_soi.models import Holding

CFG = MatchingConfig(minimum_score=5, require_unique_best_match=True, minimum_margin=1.0)


def _h(hid, **kw):
    h = Holding(cik="1", accession_number="0000000001-25-000001", holding_id=hid, holding_member_key=hid, **kw)
    return h


def _row(rid, **fields):
    return HtmlRow(0, int(rid[1:]), rid, "holding", [], "", fields_raw={k: str(v) for k, v in fields.items()}, fields=fields)


def test_match_scoring_features():
    h = _h("a", issuer="Acme Holdings LLC", description="First Lien Term Loan", fair_value=1000.0, cost=990.0, maturity_date=date(2030, 1, 1))
    r = _row("r1", issuer="Acme Holdings, LLC", description="First Lien Term Loan", fair_value=1000.0, cost=990.0, maturity_date="2030-01-01")
    score, feats, reason = score_pair(h, r)
    assert reason is None and feats["fair_value"] == 3.0 and feats["cost"] == 2.0 and feats["issuer"] == 2.0 and feats["maturity_date"] == 1.5
    assert score >= 9


def test_weak_text_only_overlap_is_rejected():
    h = _h("a", issuer="Acme Holdings LLC", fair_value=1000.0)
    r = _row("r1", issuer="Acme Holdings LLC", fair_value=55.0)
    score, feats, reason = score_pair(h, r)
    assert reason == "no_numeric_feature_and_weak_text" and score == 0.0


def test_ambiguous_match_left_unresolved():
    h1 = _h("a", issuer="Alpine Health", fair_value=4875000.0, cost=4950000.0)
    h2 = _h("b", issuer="Alpine Health", fair_value=4875000.0, cost=4950000.0)
    rows = [_row("r1", issuer="Alpine Health", fair_value=4875000.0, cost=4950000.0), _row("r2", issuer="Alpine Health", fair_value=4875000.0, cost=4950000.0)]
    recs = match_holdings([h1, h2], rows, CFG)
    assert all(r.status == "ambiguous" for r in recs) and all(r.html_row_id is None for r in recs)
    assert recs[0].best_score == recs[0].second_score


def test_description_disambiguates_identical_monetary_rows():
    h1 = _h("a", issuer="Alpine Health", description="Second Lien Term Loan", fair_value=4875000.0, cost=4950000.0)
    h2 = _h("b", issuer="Alpine Health", description="First Lien Term Loan", fair_value=4875000.0, cost=4950000.0)
    rows = [_row("r1", issuer="Alpine Health", description="Second Lien Term Loan", fair_value=4875000.0, cost=4950000.0), _row("r2", issuer="Alpine Health", description="First Lien Term Loan", fair_value=4875000.0, cost=4950000.0)]
    recs = match_holdings([h1, h2], rows, CFG)
    assert [r.html_row_id for r in recs] == ["r1", "r2"] and all(r.status == "matched" for r in recs)
    assert recs[0].margin >= 1.0


def test_one_to_one_and_minimum_score():
    h1 = _h("a", issuer="Acme", fair_value=100.0)
    h2 = _h("b", issuer="Beta", fair_value=100.0, cost=90.0)
    rows = [_row("r1", issuer="Beta", fair_value=100.0, cost=90.0)]
    recs = match_holdings([h1, h2], rows, CFG)
    assert recs[1].status == "matched" and recs[1].html_row_id == "r1"
    assert recs[0].status in {"unmatched", "ambiguous", "no_candidates"} and recs[0].html_row_id is None


def test_prefer_html_fields_supersedes_composite_text_but_not_direct_facts():
    from bdc_soi.hybrid_matcher import enrich_from_row, MatchRecord
    from bdc_soi.composite_parser import parse_rate_text

    h = _h("a", fair_value=1000.0)
    h.set_field("issuer", "Authentic Brands ABG Intermediate Holdings 2 LLC", source="parsed_composite_text", rule_id="r")
    h.set_field("fair_value", 1000.0, source="xbrl_fact", source_ref="f1")
    r = _row("r1", issuer="ABG Intermediate Holdings 2, LLC", fair_value=1001.5)
    rec = MatchRecord("a", "a", "r1", "matched", 5.0, None, None)
    enrich_from_row(h, r, rec, "table_1", lambda t: parse_rate_text(t, None), prefer_html_fields=["issuer", "fair_value"])
    assert h.issuer == "ABG Intermediate Holdings 2 LLC" and h.field_lineage["issuer"].source == "html_cell"
    assert any(c.field == "issuer" and c.alternatives[0]["source"] == "parsed_composite_text" for c in h.field_conflicts)
    assert h.fair_value == 1000.0 and "fair_value" in rec.conflicting_fields  # direct XBRL fact is never superseded


def test_description_mismatch_penalty_resolves_identical_monetary_rows():
    h1 = _h("a", issuer="Olympus", description="First Lien Secured Debt - Term Loan", fair_value=100.0, cost=99.0)
    rows = [_row("r1", issuer="Olympus", description="First Lien Secured Debt - Revolver", fair_value=100.0, cost=99.0), _row("r2", issuer="Olympus", description="First Lien Secured Debt - Term Loan", fair_value=100.0, cost=99.0)]
    recs = match_holdings([h1], rows, CFG)
    assert recs[0].status == "matched" and recs[0].html_row_id == "r2"




def test_equal_valued_group_is_matched_by_sequence_when_counts_agree():
    # PIMCO / Stellus: N identical tranches in XBRL and exactly N identical HTML rows -> document order (SPEC 14.2 table sequence).
    hs = [_h("a1", issuer="Sapphire", description="Class D Shares", fair_value=9446.0, cost=9000.0), _h("a2", issuer="Sapphire", description="Class F Shares", fair_value=9446.0, cost=9000.0)]
    rows = [_row("r1", issuer="Sapphire", description="Class D Shares", fair_value=9446.0, cost=9000.0), _row("r2", issuer="Sapphire", description="Class F Shares", fair_value=9446.0, cost=9000.0)]
    recs = match_holdings(hs, rows, CFG)
    assert [r.status for r in recs] == ["matched", "matched"] and [r.html_row_id for r in recs] == ["r1", "r2"]
    assert all("matched_by_sequence_tiebreak" in h.review_flags for h in hs) and recs[0].reason == "sequence_tiebreak_row_identity"
    # Counts differ (3 XBRL rows, 2 HTML rows): stays ambiguous.
    hs3 = hs + [_h("a3", issuer="Sapphire", description="Class G Shares", fair_value=9446.0, cost=9000.0)]
    recs3 = match_holdings(hs3, rows, CFG)
    assert all(r.status == "ambiguous" for r in recs3)
    # Identical descriptions give no pairing evidence: stays ambiguous.
    hs4 = [_h("b1", issuer="Sapphire", description="Term Loan", fair_value=5.0, cost=5.0), _h("b2", issuer="Sapphire", description="Term Loan", fair_value=5.0, cost=5.0)]
    rows4 = [_row("q1", issuer="Sapphire", description="Term Loan", fair_value=5.0, cost=5.0), _row("q2", issuer="Sapphire", description="Term Loan", fair_value=5.0, cost=5.0)]
    assert all(r.status == "matched" for r in match_holdings(hs4, rows4, CFG))  # equal descriptions pair up (document order)


def test_exact_issuer_key_separates_near_identical_share_classes():
    # Investcorp: 'ArborWorks LLC A-1 | Preferred Units' and 'ArborWorks LLC B-1 | Preferred Units' both carry 8,633 shares;
    # fuzzy issuer similarity treats A-1/B-1 as the same name, leaving the zero-value B-1 row ambiguous.
    hb = _h("b", issuer="ArborWorks LLC B-1", description="Preferred Units", fair_value=0.0, cost=0.0, shares=8633.0)
    ra = _row("r1", issuer="ArborWorks LLC A-1", description="Preferred Units", fair_value=9504469.0, cost=4362023.0, shares=8633.0)
    rb = _row("r2", issuer="ArborWorks LLC B-1", description="Preferred Units", shares=8633.0)
    sa, fa, _ = score_pair(hb, ra)
    sb, fb, _ = score_pair(hb, rb)
    assert fb.get("issuer_exact") == 1.0 and "issuer_exact" not in fa and sb - sa >= 1.0
    recs = match_holdings([hb], [ra, rb], CFG)
    assert recs[0].status == "matched" and recs[0].html_row_id == "r2"


def test_combined_par_shares_column_is_compared_against_either_xbrl_quantity():
    # Investcorp: 'Discovery Behavioral Health, LLC - Preferred Equity | 13.50% PIK | 4,000 | 4,000,000 | —' quotes a
    # rate, so the combined column value went to principal; XBRL carries 4,000 shares (and cost 4,000,000, no fair value).
    h = _h("a", issuer="Discovery Behavioral Health LLC", description="Preferred Equity", fair_value=0.0, cost=4000000.0, shares=4000.0)
    r = _row("r1", issuer="Discovery Behavioral Health LLC", description="Preferred Equity", principal_amount=4000.0, cost=4000000.0)
    r.notes.append("combined_par_shares:principal")
    score, feats, reason = score_pair(h, r)
    assert feats.get("shares_via_combined_column") == 2.0 and reason is None and score >= 5
    # Without the combined-column note the cross-field comparison does not apply.
    r2 = _row("r2", issuer="Discovery Behavioral Health LLC", description="Preferred Equity", principal_amount=4000.0, cost=4000000.0)
    assert "shares_via_combined_column" not in score_pair(h, r2)[1]


def test_contradictory_identity_is_not_merged_on_equal_values():
    # BIP Ventures 2026-06-30: XBRL member 'CareSave Technologies, Inc. ... Series E-2 Preferred Stock Acquisition Date
    # 12/12/2024' carries the figures that the HTML schedule prints for 'Integrative Life Network, LLC Class A Common
    # Stock' (251,152 / 522,718 / 142,480). Equal money with a different issuer and a different description is not a match.
    h = _h("a", issuer="CareSave Technologies Inc", description="Series E-2 Preferred Stock", fair_value=142480.0, cost=522718.0, principal_amount=251152.0)
    r = _row("r1", issuer="Integrative Life Network, LLC", description="Class A Common Stock", fair_value=142480.0, cost=522718.0, principal_amount=251152.0)
    score, feats, reason = score_pair(h, r)
    assert reason == "contradictory_identity_evidence" and score == 0.0
    recs = match_holdings([h], [r], CFG)
    assert recs[0].status == "unmatched" and recs[0].reason.startswith("contradictory_identity:r1")
    # When the HTML row is consumed by its own XBRL member the equal money is a coincidence, not a contradiction.
    own = _h("b", issuer="Integrative Life Network LLC", description="Class A Common Stock", fair_value=142480.0, cost=522718.0, principal_amount=251152.0)
    recs2 = match_holdings([h, own], [r], CFG)
    assert recs2[1].status == "matched" and recs2[0].status == "unmatched" and recs2[0].reason.startswith("contradictory_identity:r1")  # pipeline turns this into a value-coincidence flag
    # Same issuer with a different tranche description is still a candidate (issuer evidence present).
    r2 = _row("r2", issuer="CareSave Technologies, Inc.", description="Class A Common Stock", fair_value=142480.0, cost=522718.0, principal_amount=251152.0)
    assert score_pair(h, r2)[2] is None
    # Zero-value agreement (unfunded revolvers, zero-value warrants) is not money evidence, so no contradiction is raised.
    hz = _h("z", issuer="Minted Inc", description="Revolver", fair_value=0.0, cost=0.0)
    rz = _row("r3", issuer="Policy Services Company LLC", description="Warrants - Class B", fair_value=0.0, cost=0.0)
    assert score_pair(hz, rz)[2] != "contradictory_identity_evidence"


def test_group_equivalent_pairing_is_recorded_at_group_level_not_as_row_identity():
    # Breeze Aviation (Barings): XBRL 'Second Lien Senior Secured Term Loan 2' / '... 3' vs two HTML rows that both read
    # 'Second Lien Senior Secured Term Loan' with identical values: the group is equivalent, the rows are not identifiable.
    hs = [_h("a", issuer="Breeze Aviation Group Inc", description="Second Lien Senior Secured Term Loan 2", fair_value=2256000.0, cost=2300000.0),
          _h("b", issuer="Breeze Aviation Group Inc", description="Second Lien Senior Secured Term Loan 3", fair_value=2256000.0, cost=2300000.0)]
    rs = [_row("r1", issuer="Breeze Aviation Group Inc", description="Second Lien Senior Secured Term Loan", fair_value=2256000.0, cost=2300000.0),
          _row("r2", issuer="Breeze Aviation Group Inc", description="Second Lien Senior Secured Term Loan", fair_value=2256000.0, cost=2300000.0)]
    recs = match_holdings(hs, rs, CFG)
    assert [r.status for r in recs] == ["matched", "matched"] and {r.html_row_id for r in recs} == {"r1", "r2"}  # multiplicity preserved
    assert all(r.reason == "sequence_tiebreak_group_equivalent" and r.group_row_ids == ["r1", "r2"] for r in recs)
    assert all(h.identity_resolution == "group" and h.match_group_id and "group_level_identity" in h.review_flags for h in hs)
    # Distinct, exactly agreeing descriptions on both sides keep row-level identity.
    hs2 = [_h("c", issuer="Kleopatra Finco", description="Class A Common Shares", fair_value=28554.0, cost=1.0), _h("d", issuer="Kleopatra Finco", description="Class B Common Shares", fair_value=28554.0, cost=1.0)]
    rs2 = [_row("r3", issuer="Kleopatra Finco", description="Class B Common Shares", fair_value=28554.0, cost=1.0), _row("r4", issuer="Kleopatra Finco", description="Class A Common Shares", fair_value=28554.0, cost=1.0)]
    recs2 = match_holdings(hs2, rs2, CFG)
    assert [r.html_row_id for r in recs2] == ["r4", "r3"] and all(r.reason == "sequence_tiebreak_row_identity" and not r.group_row_ids for r in recs2)
    assert all(h.identity_resolution == "row" for h in hs2)


def test_reporting_currency_override_requires_documented_template_evidence():
    # D33 (revised): a '$' column symbol alone never re-assigns the reporting currency; the template must record
    # filing evidence (schedule footnote on par-column currency markers, accounting-policy note, USD total fact).
    from bdc_soi.hybrid_matcher import enrich_from_row, MatchRecord
    from bdc_soi.templates import TemplateVersion

    def pair():
        h = _h("a", issuer="Aryeh Bidco Investment Ltd", description="Term Loan", fair_value=1677000.0, cost=1842000.0, reporting_currency="CAD", fair_value_unit_original="CAD")
        r = _row("r1", issuer="Aryeh Bidco Investment Ltd", description="Term Loan", fair_value=1677000.0, cost=1842000.0)
        r.currency_symbols["fair_value"] = {"code": "USD", "symbol": "$", "source_row_id": "r0"}
        return h, r

    rec = MatchRecord("a", "a", "r1", "matched", 7.0, None, None, {})
    h, r = pair()
    enrich_from_row(h, r, rec, "table_1", lambda t: type("R", (), {f: None for f in ("reference_index", "spread", "spread_bps", "rate_floor", "pik_rate", "cash_rate", "interest_rate")})(), None, TemplateVersion(id="t", effective_from="2026-01-01"), "USD")
    assert h.reporting_currency == "CAD" and any(f.endswith("no_documented_reporting_currency_evidence") for f in h.review_flags)
    tv = TemplateVersion(id="t", effective_from="2026-01-01", validation={"reporting_currency_evidence": ["0001193125-26-341358 Note 2: accounting records maintained in U.S. dollars"]})
    h, r = pair()
    enrich_from_row(h, r, rec, "table_1", lambda t: type("R", (), {f: None for f in ("reference_index", "spread", "spread_bps", "rate_floor", "pik_rate", "cash_rate", "interest_rate")})(), None, tv, "USD")
    assert h.reporting_currency == "USD" and h.fair_value_unit_original == "CAD"
    c = next(c for c in h.field_conflicts if c.field == "reporting_currency")
    assert c.reason == "documented_reporting_currency_evidence_overrides_xbrl_unit" and any(a.get("source") == "template_reporting_currency_evidence" for a in c.alternatives)
