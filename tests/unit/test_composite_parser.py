from datetime import date

from bdc_soi.composite_parser import GENERIC_RATE_PATTERN, apply_composite_rule, as_output_dict, parse_rate_text, resolve_index, split_industry_prefix
from bdc_soi.normalization import bps_to_decimal, decimal_to_bps, normalize_issuer, parse_date, percent_to_decimal, text_key
from bdc_soi.templates import CompositeField, HeaderParser, NormalizationSpec, RateParser

RULE = CompositeField(
    id="member-label-layout-v1",
    source_field="issuer_name",
    pattern=r"^(?P<header>.+?)\s+Investment Type\s+(?P<description>.+?)\s+Interest Rate\s+(?P<rate>.+?)\s+Maturity Date\s+(?P<maturity>\d{1,2}/\d{1,2}/\d{4})$",
    header_parser=HeaderParser(known_industries=["Software", "Healthcare", "Business Services", "Financial Services"], industry_position="prefix", remainder_target="issuer_name"),
    rate_parser=RateParser(pattern=r"(?P<index>SOFR|S|LIBOR|L|PRIME|P)\s*\+\s*(?P<spread_bps>\d+(?:\.\d+)?)", floor_pattern=r"(?P<floor_pct>\d+(?:\.\d+)?)\s*%\s*Floor", index_aliases={"S": "SOFR", "SOFR": "SOFR", "L": "LIBOR", "LIBOR": "LIBOR", "P": "Prime", "PRIME": "Prime"}),
)
NORM = NormalizationSpec(date_formats=["%m/%d/%Y", "%Y-%m-%d"], spread_input_unit="basis_points", spread_output_format="percent")
REDWOOD = "Software Redwood Runway Bidco, LLC Investment Type First Lien Secured Debt - Term Loan Interest Rate S+450, 0.50% Floor Maturity Date 12/17/2031"


def test_spec_22_2_redwood_example_exact():
    res = apply_composite_rule(RULE, REDWOOD, NORM)
    assert res.matched and res.rule_id == "member-label-layout-v1"
    out = as_output_dict(res)
    out.setdefault("issue_date", None)
    expected = {
        "issuer": "Redwood Runway Bidco LLC",
        "description": "First Lien Secured Debt - Term Loan",
        "industry": "Software",
        "reference_index": "SOFR",
        "spread": 0.045,
        "spread_bps": 450,
        "rate_floor": 0.005,
        "issue_date": None,
        "maturity_date": "2031-12-17",
    }
    assert {k: out.get(k) for k in expected} == expected
    assert res.fields["issuer"].raw == "Software Redwood Runway Bidco, LLC" and res.fields["maturity_date"].value == date(2031, 12, 17)
    assert "issue_date" not in res.fields  # never inferred


def test_spread_conversions():
    assert bps_to_decimal(450) == 0.045 and percent_to_decimal(0.50) == 0.005 and decimal_to_bps(0.045) == 450.0


def test_percent_formatted_spread_is_not_treated_as_bps():
    rr = parse_rate_text("SOFR + 4.50%, 0.50% Floor", RULE.rate_parser, NORM)
    assert rr.reference_index == "SOFR" and rr.spread_bps == 450.0 and rr.spread == 0.045 and rr.rate_floor == 0.005
    assert any("percent_sign_after_bps_capture" in d for d in rr.diagnostics)
    rr2 = parse_rate_text("S+450, 0.50% Floor", RULE.rate_parser, NORM)
    assert rr2.spread_bps == 450.0 and rr2.spread == 0.045 and not rr2.diagnostics


def test_other_rate_formats():
    assert parse_rate_text("L+600", RULE.rate_parser).reference_index == "LIBOR"
    assert parse_rate_text("L+600", RULE.rate_parser).spread_bps == 600
    p = parse_rate_text("Prime + 2.25%", RateParser(pattern=r"(?P<index>SOFR|S|LIBOR|L|Prime|PRIME|P)\s*\+\s*(?P<spread_bps>\d+(?:\.\d+)?)", index_aliases={"Prime": "Prime"}))
    assert p.reference_index == "Prime" and p.spread == 0.0225
    pik = parse_rate_text("S+400 cash / 2.00% PIK", RULE.rate_parser)
    assert pik.spread_bps == 400 and pik.pik_rate == 0.02
    fixed = parse_rate_text("10.50%", RULE.rate_parser)
    assert fixed.interest_rate == 0.105 and fixed.spread is None


def test_reference_index_aliasing_is_template_specific():
    assert resolve_index("S", {"S": "SOFR"})[0] == "SOFR"
    assert resolve_index("S", {})[0] is None  # no global assumption that S means SOFR
    assert resolve_index("SOFR", {})[0] == "SOFR"  # unambiguous generic alias
    assert resolve_index("Term SOFR", {})[0] == "SOFR"


def test_industry_prefix_only_on_exact_configured_match():
    assert split_industry_prefix("Software Redwood Runway Bidco, LLC", ["Software"]) == ("Software", "Redwood Runway Bidco, LLC")
    assert split_industry_prefix("Softwareish Co", ["Software"]) == (None, "Softwareish Co")
    assert split_industry_prefix("Redwood Software Co", ["Software"]) == (None, "Redwood Software Co")
    res = apply_composite_rule(RULE, "Aerospace Redwood Runway Bidco, LLC Investment Type Loan Interest Rate S+450 Maturity Date 12/17/2031", NORM)
    assert "industry" not in res.fields and res.fields["issuer"].value == "Aerospace Redwood Runway Bidco LLC"
    res2 = apply_composite_rule(RULE, "Aerospace Redwood Runway Bidco, LLC Investment Type Loan Interest Rate S+450 Maturity Date 12/17/2031", NORM, independent_industry="Aerospace")
    assert res2.fields["industry"].value == "Aerospace" and res2.fields["issuer"].value == "Redwood Runway Bidco LLC"


def test_remainder_pattern_extracts_legal_name_from_duplicated_short_name():
    # Observed in Apollo Debt Solutions 10-Q: "{Industry} {Short name} {Legal name} Investment Type ...".
    rule = RULE.model_copy(update={"header_parser": HeaderParser(known_industries=["Aerospace & Defense"], remainder_pattern=r"^(?P<short>.+?)\s+(?P<issuer>(?P=short)\b.*)$")})
    text = "Aerospace & Defense Accel International Accel International Holdings, LLC Investment Type First Lien Secured Debt - Revolver Interest Rate S+425, 0.50% Floor Maturity Date 04/26/2032"
    res = apply_composite_rule(rule, text, NORM)
    assert res.fields["industry"].value == "Aerospace & Defense" and res.fields["issuer"].value == "Accel International Holdings LLC"
    assert res.fields["description"].value == "First Lien Secured Debt - Revolver" and res.fields["spread_bps"].value == 425


def test_date_normalization():
    assert parse_date("12/17/2031", ["%m/%d/%Y"]) == (date(2031, 12, 17), None)
    assert parse_date("2031-12-17")[0] == date(2031, 12, 17)
    assert parse_date("13/17/2031", ["%m/%d/%Y"])[0] is None
    assert parse_date("—")[0] is None
    assert parse_date("01/02/2030", ["%m/%d/%Y", "%d/%m/%Y"]) == (None, "ambiguous_date:01/02/2030")


def test_issuer_normalization_and_text_key():
    assert normalize_issuer("Redwood Runway Bidco, LLC") == "Redwood Runway Bidco LLC"
    assert normalize_issuer("Acme, Inc.") == "Acme Inc"
    assert normalize_issuer("Acme Holdings (4)") == "Acme Holdings"
    assert text_key("Redwood Runway Bidco, LLC") == text_key("redwood runway bidco llc")


def test_additional_rate_formats_observed_in_apollo_labels():
    cp = parse_rate_text("5.38% Cash plus 5.38% PIK, 0.00% Floor", RULE.rate_parser)
    assert cp.matched and cp.cash_rate == 0.0538 and cp.pik_rate == 0.0538 and abs(cp.interest_rate - 0.1076) < 1e-9 and cp.rate_floor == 0.0
    po = parse_rate_text("12.50% PIK", RULE.rate_parser)
    assert po.matched and po.pik_rate == 0.125 and po.interest_rate == 0.125 and po.spread is None
    assert parse_rate_text("N+475, 0.00% Floor", RULE.rate_parser).reference_index is None  # N is not aliased in this template


def test_industry_prefix_tolerates_ampersand_vs_and():
    assert split_industry_prefix("Paper & Forest Products 48forty Solutions", ["Paper And Forest Products"]) == ("Paper & Forest Products", "48forty Solutions")


def test_na_dates_are_null_without_diagnostic():
    assert parse_date("N/A") == (None, "empty")


def test_audax_style_rate_text_with_percent_spread_and_interest_rate_pattern():
    rp = RateParser(pattern=r"(?P<index>[A-Z]+)\s*\+\s*Spread\s+(?P<spread_pct>\d+(?:\.\d+)?)%", interest_rate_pattern=r"Interest Rate\s+(?P<rate_pct>\d+(?:\.\d+)?)%", index_aliases={"S": "SOFR"})
    rr = parse_rate_text("S + Spread 4.75% Interest Rate 8.48%", rp)
    assert rr.reference_index == "SOFR" and rr.spread == 0.0475 and rr.spread_bps == 475 and rr.interest_rate == 0.0848


def test_delimited_composite_rule():
    rule = CompositeField(id="pipe", source_field="issuer", kind="delimited", delimiter="|", positions={"ignore": 0, "issuer": 1, "description": 2, "industry": 3, "rate": 4, "interest_rate": 5, "maturity": 7}, min_parts=4, rate_parser=RateParser(pattern=r"(?P<index>SOFR|Prime)\s*\+\s*(?P<spread_pct>\d+(?:\.\d+)?)", spread_unit="percent", index_aliases={"SOFR": "SOFR"}))
    res = apply_composite_rule(rule, "Debt Investments | AMI Buyer, Inc. | First Lien Senior Secured Term Loan | Semiconductors & Semiconductor Equipment | SOFR + 5.000 |8.698%| 10/17/2024 | 10/17/2031", NORM)
    out = as_output_dict(res)
    assert res.matched and out["issuer"] == "AMI Buyer Inc" and out["description"] == "First Lien Senior Secured Term Loan" and out["industry"] == "Semiconductors & Semiconductor Equipment"
    assert out["reference_index"] == "SOFR" and out["spread_bps"] == 500 and out["maturity_date"] == "2031-10-17"
    short = apply_composite_rule(rule, "Debt Investments | AMI Buyer, Inc. | Revolver", NORM)
    assert not short.matched and short.diagnostics


def test_infix_industry_and_rate_capture_coercion():
    assert split_industry_prefix("Investments – non-controlled / affiliated Convertible Notes Healthcare Peregrine Health, Inc", ["Healthcare"], "infix") == ("Healthcare", "Peregrine Health, Inc")
    rule = CompositeField(id="r", source_field="issuer", pattern=r"^(?P<issuer>.+?) \| (?P<interest_rate>[\d.]+%) \| (?P<reference_index>[A-Z]+)$", rate_parser=RateParser(pattern="x", index_aliases={"S": "SOFR"}))
    res = apply_composite_rule(rule, "Acme | 8.698% | S", NORM)
    assert res.fields["interest_rate"].value == 0.08698 and res.fields["reference_index"].value == "SOFR"
    gen = parse_rate_text("3M SOFR + 5.25%", None)
    assert gen.reference_index == "SOFR" and gen.spread_bps == 525
    assert parse_rate_text("SOFR(Q) + 4.25%", None).spread == 0.0425 and parse_rate_text("1 Month SOFR USD + 5.00%", None).spread_bps == 500
    assert parse_rate_text("S +CSA + 3.75%", RateParser(pattern=GENERIC_RATE_PATTERN.replace("SOFR|", "SOFR|S|"), index_aliases={"S": "SOFR"})).spread_bps == 375
