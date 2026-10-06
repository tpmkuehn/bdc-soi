"""Regression checks for the Apollo Debt Solutions template rules against label formats observed in
accession 0001193125-26-341358 (offline; label strings copied from the filing's typed members)."""

from pathlib import Path

import pytest

from bdc_soi.composite_parser import apply_composite_rule
from bdc_soi.templates import load_template_file

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def apollo():
    lt = load_template_file(ROOT / "templates" / "1837532.yml")
    assert lt.issues == []
    return lt.file.templates[0]


def _parse(tv, text):
    out = {}
    for rule in tv.composite_fields:
        res = apply_composite_rule(rule, text, tv.normalization)
        if res.matched:
            for k, v in res.fields.items():
                out.setdefault(k, v.value)
            out.setdefault("_rule", rule.id)
    return out


def test_layout_v1_with_duplicated_short_name(apollo):
    o = _parse(apollo, "Aerospace & Defense Accel International Accel International Holdings, LLC Investment Type First Lien Secured Debt - Revolver Interest Rate S+425, 0.50% Floor Maturity Date 04/26/2032")
    assert o["industry"] == "Aerospace & Defense" and o["issuer"] == "Accel International Holdings LLC"
    assert o["description"] == "First Lien Secured Debt - Revolver" and o["reference_index"] == "SOFR" and o["spread_bps"] == 425 and o["spread"] == 0.0425 and o["rate_floor"] == 0.005
    assert o["maturity_date"].isoformat() == "2032-04-26" and o["_rule"] == "apollo-member-label-layout-v1"


def test_layout_v1_without_interest_rate_keyword(apollo):
    o = _parse(apollo, "Commercial Services & Supplies Pritchard Industries Pritchard Industries, LLC Investment Type First Lien Secured Debt - Term Loan S+590, 0.75% Floor Maturity Date 10/13/2027")
    assert o["description"] == "First Lien Secured Debt - Term Loan" and o["spread_bps"] == 590 and o["maturity_date"].isoformat() == "2027-10-13"


def test_layout_v2_without_type_keyword(apollo):
    o = _parse(apollo, "Software G2CI Evergreen IX Borrower 2023 LLC First Lien Secured Debt - Term Loan S+475, 0.75% Floor Maturity Date 9/30/2030")
    assert o["_rule"] == "apollo-member-label-layout-v2" and o["industry"] == "Software" and o["description"] == "First Lien Secured Debt - Term Loan"
    assert o["spread_bps"] == 475 and o["maturity_date"].isoformat() == "2030-09-30"


def test_equity_label_without_rate_or_maturity(apollo):
    o = _parse(apollo, "Chemicals Rochester Midland Corporation RMC Topco LLC Investment Type Common Equity - Equity Unit")
    assert o["industry"] == "Chemicals" and o["description"] == "Common Equity - Equity Unit" and "maturity_date" not in o and "spread" not in o


def test_company_specific_index_letters(apollo):
    o = _parse(apollo, "Media X Y Investment Type First Lien Secured Debt - Term Loan Interest Rate N+475, 0.00% Floor Maturity Date 08/26/2032")
    assert o["reference_index"] == "NIBOR" and o["spread_bps"] == 475 and o["rate_floor"] == 0.0
