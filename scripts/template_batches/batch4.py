"""Batch 4 templates: SCP Private Credit Income BDC, SLR HC BDC, SLR Private Credit BDC II, Stellus Private Credit BDC,
TriplePoint Venture Growth BDC, West Bay BDC."""

from template_batches.batch1 import DATE, base, hdr  # type: ignore
from template_batches.batch2 import GS_RP  # type: ignore

TEMPLATES = {}
SLR_RP = {"pattern": r"(?P<index>S|P|SOFR|Prime)\s*\+\s*(?P<spread_bps>\d+)(?!\.\d)(?!\s*%)", "spread_unit": "basis_points", "index_aliases": {"S": "SOFR", "SOFR": "SOFR", "P": "Prime", "Prime": "Prime"}}
SLR_HTML = {"header_aliases": {"issuer_name": ["^Description"], "industry": ["^Industry"], "interest_rate_text": ["^Spread above Index"], "rate_floor": ["^Floor"], "interest_rate": ["^Interest Rate"], "cost": ["^Cost"], "fair_value": ["^Fair Value"], "maturity_date": ["^Maturity Date"], "principal_amount": ["^Par Amount"], "shares": ["^Shares"]},
            "row_rules": {"carry_forward": [], "group_heading_target": "investment_type", "group_heading_rules": [{"regex": "affiliated|controlled", "target": "affiliate_status"}], "total_if_regex": ["^Total Investments\\b(?!\\s*\\(?\\d*\\)?\\s*(?:&|and)\\s+Cash)(?!\\s+in\\s)"], "subtotal_if_regex": ["^Total\\b"], "require_any_numeric": ["fair_value", "cost", "principal_amount", "shares"]},
            "rate_parser": SLR_RP, "prefer_html_fields": ["issuer_name"]}
SLR_NORM = {"legal_suffixes": {"remove_preceding_comma": True}, "date_formats": ["%m/%d/%Y", "%Y-%m-%d"], "spread_input_unit": "basis_points", "spread_output_format": "decimal", "reference_index_aliases": {"S": "SOFR", "P": "Prime"}}

# ---------------------------------------------------------------- SCP Private Credit Income BDC (1743415)
TEMPLATES["1743415"] = (base(
    "1743415", "SCP Private Credit Income BDC LLC", "scp-private-credit-2026-layout-v1", "2026-03-31",
    "SLR-managed layout. Typed labels: 'Bank Debt/Senior Secured Loans — {Issuer} Industry {Industry} Spread above Index S+525 Floor 0.75% Interest Rate 9.57% Acquisition Date M/YYYY Maturity Date M/YYYY' (basis-point spreads, month/year dates). HTML SOI in thousands: 'Description | Industry | Spread above Index | Floor | Interest Rate | Acquisition Date | Maturity Date | Par Amount | Cost | Fair Value'; grand total 'Total Investments(9) — 103.2%' (the row 'Total Investments & Cash Equivalents' is not the SOI total).",
    ["0001193125-26-332724 (2026-06-30): 19 typed members; HTML 'Total Investments(9) $151,605 $131,073' matches the holdings sums; no undimensioned XBRL total facts",
     "0001193125-26-332724: 'S' supported by InvestmentVariableInterestRateTypeExtensibleEnumeration = SOFR on 11 members",
     "0001193125-26-206308 (2026-03-31) inspected as the prior period"],
    html=SLR_HTML,
    composite_fields=[{"id": "scp-label-v1", "source_field": "issuer_name", "applies_to": "xbrl",
                       "pattern": r"^(?P<investment_type>[^—]+?)\s+—\s+(?P<issuer>.+?)\s+Industry\s+(?P<industry>.+?)(?:\s+Spread above Index\s+(?P<rate>\S+))?(?:\s+Floor\s+(?P<rate_floor>\d+(?:\.\d+)?%))?(?:\s+Interest Rate\s+(?P<interest_rate>\d+(?:\.\d+)?%))?(?:\s+Acquisition Date\s+\d{1,2}/\d{4})?(?:\s+Maturity Date\s+\d{1,2}/\d{4})?$",
                       "rate_parser": SLR_RP}],
    normalization=SLR_NORM,
), hdr("SCP Private Credit Income BDC LLC", "1743415", "0001193125-26-332724", "2026-06-30"))

# ---------------------------------------------------------------- SLR HC BDC (1832148) and SLR Private Credit BDC II (1932591)
for cik, name, tid, acc, prior, members in (("1832148", "SLR HC BDC LLC", "slr-hc-bdc-2026-layout-v1", "0001193125-26-332723", "0001193125-26-206309", "37 typed members"),
                                             ("1932591", "SLR Private Credit BDC II LLC", "slr-private-credit-ii-2026-layout-v1", "0001193125-26-332722", "0001193125-26-206310", "33 typed members")):
    TEMPLATES[cik] = (base(
        cik, name, tid, "2026-03-31",
        "SLR-managed layout. Typed labels are pipe-delimited: 'Bank Debt/Senior Secured Loans[ — x%] | {Issuer} | {Industry} | S+525 | 1.00% | 8.98% | M/YYYY | M/YYYY' (section, issuer, industry, spread in basis points, floor, interest rate, acquisition, maturity). HTML SOI in thousands: 'Description | Industry | Spread above Index | Floor | Interest Rate | Acquisition Date | Maturity Date | Par Amount | Cost | Fair Value'; month/year maturities are left null.",
        [f"{acc} (2026-06-30): {members}; HTML grand total 'Total Investments' equals the holdings sums (fair value and cost pass)",
         f"{acc}: 'S' supported by InvestmentVariableInterestRateTypeExtensibleEnumeration = SOFR; spreads are basis points ('S+525' with XBRL spread 0.0525)",
         f"{prior} (2026-03-31) inspected as the prior period"],
        html=SLR_HTML,
        composite_fields=[{"id": "slr-pipe-label-v1", "source_field": "issuer_name", "applies_to": "xbrl", "kind": "delimited", "delimiter": "|", "positions": {"investment_type": 0, "issuer": 1, "industry": 2, "rate": 3, "rate_floor": 4, "interest_rate": 5}, "min_parts": 3, "rate_parser": SLR_RP}],
        normalization=SLR_NORM,
    ), hdr(name, cik, acc, "2026-06-30"))

# ---------------------------------------------------------------- Stellus Private Credit BDC (1901037)
TEMPLATES["1901037"] = (base(
    "1901037", "Stellus Private Credit BDC", "stellus-private-credit-2026-layout-v1", "2026-03-31",
    "XBRL carries issuer, industry, affiliation and type as extensible enumerations; typed labels are '{Issuer}, {Description}'. HTML SOI in whole dollars with zero-width-space padded headers: 'Investments | Footnotes | Security | Coupon | Floor | Cash | PIK | Investment Date | Maturity | Principal | Amortized Cost | Fair Value'.",
    ["0001104659-26-094771 (2026-06-30): 337 typed members; undimensioned fair value 419,527,201 and cost 410,125,150 within tolerance of the holdings sums; enumeration values 'Three Month Sofr'/'One Month Sofr'/'Six Month Sofr'",
     "0001104659-26-094771 HTML: a blank first row precedes three header rows whose words are split ('Principal' / 'Amount/' / 'Shares (3)', 'Amortized' / 'Cost', 'Fair' / 'Value (1)') and every other cell is a zero-width-space spacer; reconstruction keeps original cell text and strips the invisible characters only in the parsing representation (iteration 010); partial-word aliases retained for robustness",
     "0001104659-26-059217 (2026-03-31) inspected as the prior period",
     "0001104659-26-094771 HTML tables 10-18: the portfolio company is a heading row ('Bart & Associates, LLC | (4) | ... | McLean, VA'); the 'Investments' column holds the security ('Term Loan', 'Sapphire Aggregator S.a r.l. Class G Shares') and 'Security' holds the type ('First Lien', 'Equity'); typed labels are '{Portfolio company}, {security}' (e.g. 'Monitorus Holding LLC, Sapphire Aggregator S.a r.l. Class G Shares', 'Champion Services Acquireco LLC, Term Loan (PBDC SPV)') or '{Portfolio company} {security}' without a comma ('AdCellerant LLC Term A Loan')"],
    html={"disabled": False,
          "table_detection": {"heading_regex": ["Schedule of Investments"], "required_terms": ["Fair"], "optional_terms": ["Amortized", "Principal"], "excluded_terms": ["Fair Value Hierarchy", "Financial Highlights", "% of Total Investments"], "minimum_score": 6, "max_heading_distance": 20},
          "header_aliases": {"security_description": ["^Investments?$"], "industry": ["^Headquarters"], "investment_type": ["^Security"], "interest_rate": ["^Coupon"], "rate_floor": ["^Floor"], "cash_rate": ["^Cash$"], "pik_rate": ["^PIK"], "cost": ["^Amortized(?: Cost)?$"], "fair_value": ["^Fair(?: Value)?$"], "maturity_date": ["^Maturity"], "principal_amount": ["^Principal"], "footnote_markers": ["^Footnotes"], "percent_of_net_assets": ["^% of Net"]},
          "scale": {"source": "fixed", "fixed_multiplier": 1, "default": 1},
          "row_rules": {"carry_forward": [], "group_heading_target": "issuer_name", "group_heading_rules": [{"regex": "affiliated|controlled", "target": "affiliate_status"}], "total_if_regex": ["^Total Investments\\b(?!\\s+in\\s)"], "subtotal_if_regex": ["^Total\\b"], "require_any_numeric": ["fair_value", "cost", "principal_amount", "shares"]},
          "prefer_html_fields": []},
    composite_fields=[{"id": "stellus-label-v1", "source_field": "issuer_name", "applies_to": "xbrl",
                       "pattern": r"^(?P<issuer>.+?(?:, (?:LLC|Inc\.?|L\.P\.|LP|Ltd\.?|Corp\.?))?),? (?P<description>(?:Term Loan|Term [A-Z] Loan|Revolver(?: One| Two)?|Delayed Draw[^,]*|Class [A-Z]-?\d* (?:Units|Shares)|Preferred Stock|Common Stock|Warrants?|Equity|LP Interest|Convertible Bonds|Calss A Units|(?<=, )[^,]+)(?: \(PBDC SPV\))?)$"}],
    normalization={"legal_suffixes": {"remove_preceding_comma": True}, "date_formats": ["%m/%d/%Y", "%Y-%m-%d"], "spread_input_unit": "percent", "spread_output_format": "decimal", "reference_index_aliases": {}},
    validation={"reporting_currency_evidence": ['0001104659-26-094771, Consolidated Schedule of Investments footnote: \'Par amount is denominated in U.S. Dollars ("$") unless otherwise noted in Euros ("€").\' (table_15 rows t15r48-t15r50 print \'€1,353,050\' in the par column and USD cost/fair value)', "0001104659-26-094771, Note 2: 'The accounting records of the Company are maintained in U.S. dollars.' and 'Foreign currency amounts are translated into U.S. dollars ...'"]},
), hdr("Stellus Private Credit BDC", "1901037", "0001104659-26-094771", "2026-06-30"))

# ---------------------------------------------------------------- TriplePoint Venture Growth BDC (1580345)
TPVG_RP = {"pattern": r"\((?P<index>Prime|SOFR)\s*\+\s*(?P<spread_pct>\d+(?:\.\d+)?)\s*%\s*interest rate", "floor_pattern": r"(?P<floor_pct>\d+(?:\.\d+)?)\s*%\s*floor", "spread_unit": "percent", "index_aliases": {"Prime": "Prime", "SOFR": "SOFR"}}
TEMPLATES["1580345"] = (base(
    "1580345", "TriplePoint Venture Growth BDC Corp.", "triplepoint-venture-growth-2026-layout-v1", "2026-03-31",
    "Typed labels are pipe-delimited 'Issuer | Description | Section' (e.g. 'Radar Labs, Inc. | Preferred Stock | Equity Investments'). HTML SOI in thousands with title rows repeating the schedule name; debt rows carry the rate inside the investment type text: 'Growth Capital Loan (Prime + 5.50% interest rate, 12.25% floor, 5.00% EOT payment)'; separate warrant/equity tables with 'Shares | Cost | Fair Value'.",
    ["0001580345-26-000025 (2026-06-30): 340 typed members (29 without monetary facts); undimensioned cost 830,835,000 equals the holdings sum; fair value 780,742,000 within tolerance of XBRL-only rows",
     "0001580345-26-000021 (2026-03-31) inspected as the prior period",
     "0001580345-26-000025 HTML table_15 rows 31-33: additional tranches of the same issuer (Lively, Inc. Growth Capital Loan x3) leave the Portfolio Company cell blank; XBRL carries three 'Lively Inc | Growth Capital Loan' members, so the issuer carries forward within a group",
     "0001580345-26-000021 (2026-03-31): typed labels carry the affiliation as a further pipe segment ('Bestow Inc. | Preferred Stock 3 | Equity Investments  |Non-Affiliated Issuer'; debt rows 'Lively, Inc. | Growth Capital Loan | Non-Affiliated'); the earlier positional rule wrote 'Non-Affiliated' into investment_type for 101 rows, so the label rule names the section vocabulary (Debt/Equity/Warrant Investments) and maps the affiliation to affiliate_status",
     "0001580345-26-000025 HTML table_25 row 13: 'Total Investments in Portfolio Companies - 221.28%*(9)(11) $ 830,835 $ 780,742' equals the undimensioned XBRL cost/fair value totals and is the schedule's grand total; the 'Cash Equivalents' money-market fund (13,582) follows it outside the total"],
    html={"header_aliases": {"issuer_name": ["^Portfolio Company"], "security_description": ["^Type of Investment", "^Type of Warrant", "^Type of Equity"], "cost": ["^Cost"], "fair_value": ["^Fair Value"], "maturity_date": ["^Maturity Date"], "principal_amount": ["^Principal Amount"], "shares": ["^Shares"]},
          "row_rules": {"carry_forward": ["issuer_name"], "group_heading_target": "industry", "group_heading_rules": [{"regex": "affiliated|controlled", "target": "affiliate_status"}, {"regex": "^(Debt Investments|Warrant Investments|Equity Investments)", "target": "investment_type"}], "total_if_regex": ["^Total Investments in Portfolio Companies\\b", "^Total Investments\\b(?!\\s+in\\s)", "^Total investments\\b(?!\\s+in\\s)"], "subtotal_if_regex": ["^Total\\b"], "require_any_numeric": ["fair_value", "cost", "principal_amount", "shares"]},
          "rate_parser": TPVG_RP, "prefer_html_fields": ["issuer_name"]},
    composite_fields=[{"id": "tpvg-pipe-label-v1", "source_field": "issuer_name", "applies_to": "xbrl",
                       "pattern": r"^(?P<issuer>[^|]+?)\s*\|\s*(?P<description>[^|]+?)\s*(?:\|\s*(?P<investment_type>(?:Debt|Equity|Warrant) Investments)\s*)?(?:\|?\s*(?P<affiliate_status>(?:Non-)?Affiliated(?: Issuer)?|Controlled(?: Issuer)?)\s*)?\|?\s*$"},
                      {"id": "tpvg-html-rate-in-description-v1", "source_field": "security_description", "applies_to": "html", "pattern": r"^(?P<description>[^(]+?)\s*\((?P<rate>.+?)\)\s*$", "rate_parser": TPVG_RP}],
    normalization={"legal_suffixes": {"remove_preceding_comma": True}, "date_formats": ["%m/%d/%Y", "%Y-%m-%d"], "spread_input_unit": "percent", "spread_output_format": "decimal", "reference_index_aliases": {}},
), hdr("TriplePoint Venture Growth BDC Corp.", "1580345", "0001580345-26-000025", "2026-06-30"))

# ---------------------------------------------------------------- West Bay BDC (2020354)
TEMPLATES["2020354"] = (base(
    "2020354", "West Bay BDC LLC", "west-bay-bdc-2026-layout-v1", "2026-03-31",
    "Goldman Sachs-managed layout. Typed labels: '{Section} - x% {Country} - x% {Security type} - x% {Issuer} Industry {Industry} [Interest Rate 8.49%] Reference Rate and Spread S + 4.75% Maturity MM/DD/YY'. HTML SOI in thousands: 'Investment | Industry | Interest Rate | Reference Rate and Spread | Maturity | Par/Shares | Cost | Fair Value | Footnotes' with section/country/security-type headings; an affiliated money-market fund is listed after the investments total.",
    ["0001193125-26-344618 (2026-06-30): 148 typed members; undimensioned fair value 608,548,000 and cost 613,539,000 within tolerance of the XBRL holdings sums; HTML 'Total Debt Investments $613,539 $608,548'",
     "0001193125-26-344618: index letters S/P/E supported by InvestmentVariableInterestRateTypeExtensibleEnumeration (SOFR 145, Prime 1, EURIBOR 1); 53 negative fair-value facts on unfunded facilities",
     "0001193125-26-219870 (2026-03-31) inspected as the prior period"],
    html={"header_aliases": {"issuer_name": ["^Investment"], "industry": ["^Industry"], "interest_rate": ["^Interest Rate"], "interest_rate_text": ["^Reference Rate and Spread"], "cost": ["^Cost"], "fair_value": ["^Fair Value"], "maturity_date": ["^Maturity"], "principal_amount": ["^Par"], "footnote_markers": ["^Footnotes"]},
          "row_rules": {"carry_forward": [], "group_heading_target": "investment_type", "group_heading_rules": [{"regex": "affiliated|controlled", "target": "affiliate_status"}, {"regex": "^(United States|Canada|United Kingdom|India|Australia|Europe|Netherlands|Germany|France|Luxembourg|Ireland|Spain|Sweden|Norway|Denmark|Belgium|Italy|Switzerland|Israel|Singapore|Japan)\\b", "target": "country"}], "total_if_regex": ["^Total Debt Investments\\b", "^Total Investments\\b(?!\\s+in\\s)"], "subtotal_if_regex": ["^Total\\b"], "require_any_numeric": ["fair_value", "cost", "principal_amount", "shares"]},
          "rate_parser": GS_RP, "prefer_html_fields": ["issuer_name"]},
    composite_fields=[{"id": "west-bay-label-v1", "source_field": "issuer_name", "applies_to": "xbrl",
                       "pattern": r"^(?P<investment_type>.+?) - \d+(?:\.\d+)?%\s+(?P<country>.+?) - \d+(?:\.\d+)?%\s+(?P<security>.+?) - \d+(?:\.\d+)?%\s+(?P<issuer>.+?)\s+Industry\s+(?P<industry>.+?)(?:\s+Interest Rate\s+(?P<interest_rate>\d+(?:\.\d+)?%))?(?:\s+Reference Rate and Spread\s+(?P<rate>.+?))?(?:\s+Maturity\s+(?P<maturity>\d{2}/\d{2}/\d{2}))?(?:\s+Acquisition Date.*)?$",
                       "capture_targets": {"security": "description"}, "rate_parser": GS_RP}],
    normalization={"legal_suffixes": {"remove_preceding_comma": True}, "date_formats": ["%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"], "spread_input_unit": "percent", "spread_output_format": "decimal", "reference_index_aliases": {"S": "SOFR", "P": "Prime", "E": "EURIBOR"}},
    validation={"allow_negative_fair_value": True, "allow_negative_fair_value_evidence": "0001193125-26-344618: 53 negative InvestmentOwnedAtFairValue facts on unfunded facilities."},
), hdr("West Bay BDC LLC", "2020354", "0001193125-26-344618", "2026-06-30"))
