"""Regression checks for the Audax Credit BDC template against label formats observed in accession
0001193125-26-348682 (offline; label strings copied from the filing's typed members)."""

from pathlib import Path

import pytest

from bdc_soi.composite_parser import apply_composite_rule
from bdc_soi.templates import load_template_file

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def audax():
    lt = load_template_file(ROOT / "templates" / "1633858.yml")
    assert lt.issues == []
    return lt.file.templates[0]


def _parse(tv, text):
    for rule in tv.composite_fields:
        res = apply_composite_rule(rule, text, tv.normalization)
        if res.matched:
            return {k: v.value for k, v in res.fields.items()} | {"_rule": rule.id}
    return {}


def test_section_label_with_percent_spread(audax):
    o = _parse(audax, "Ptfl Inv Audax Credit BDC, Inc. BNK LNS: NCNA Inv Beverage, Food & Tobacco Mary Ruth's Investment Type 1st Lien Term Loan Index S + Spread 4.75% Interest Rate 8.48% Acquisition Date 9/26/2025 Maturity Date 9/30/2031")
    assert o["_rule"] == "audax-member-label-section-v1"
    assert o["industry"] == "Beverage, Food & Tobacco" and o["issuer"] == "Mary Ruth's" and o["description"] == "1st Lien Term Loan"
    assert o["reference_index"] == "SOFR" and o["spread"] == 0.0475 and o["spread_bps"] == 475 and o["interest_rate"] == 0.0848
    assert o["maturity_date"].isoformat() == "2031-09-30" and "issue_date" not in o  # acquisition date is not an issue date


def test_commitment_label(audax):
    o = _parse(audax, "Investment A1 Garage Door Investment Type Senior Secured Revolving Loan Index S+ Spread 4.50% Interest Rate 8.48% Maturity 12/22/2028")
    assert o["_rule"] == "audax-member-label-commitment-v1" and o["issuer"] == "A1 Garage Door" and o["description"] == "Senior Secured Revolving Loan"
    assert o["spread_bps"] == 450 and o["maturity_date"].isoformat() == "2028-12-22"


def test_unknown_industry_stays_in_issuer(audax):
    o = _parse(audax, "Ptfl Inv Audax Credit BDC, Inc. BNK LNS: NCNA Inv Quantum Widgets Acme Co Investment Type 1st Lien Term Loan Index S + Spread 5.00% Interest Rate 8.73% Maturity Date 9/4/2029")
    assert "industry" not in o and o["issuer"] == "Quantum Widgets Acme Co"


def test_equity_section_label(audax):
    o = _parse(audax, "Portfolio Investments EQUITY AND PREFERRED SHARES: NON-CONTROL/NON-AFFILIATE INVESTMENTS Services: Business OSG Billing Services Investment Type Class A Units Acquisition Date 11/30/2023")
    assert o["_rule"] == "audax-member-label-equity-section-v1" and o["industry"] == "Services: Business" and o["issuer"] == "OSG Billing Services"
    assert o["description"] == "Class A Units" and o["affiliate_status"] == "EQUITY AND PREFERRED SHARES: NON-CONTROL/NON-AFFILIATE INVESTMENTS" and "maturity_date" not in o
