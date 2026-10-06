"""Batch 3 templates: Kayne Anderson BDC, Muzinich BDC, New Mountain Guardian IV, Onex Direct Lending, PIMCO Capital Solutions, Palmer Square."""

from template_batches.batch1 import DATE, base, hdr  # type: ignore
from write_templates import html_industry_headings  # type: ignore

TEMPLATES = {}
PCT = {"spread_unit": "percent"}

# ---------------------------------------------------------------- Kayne Anderson BDC (1747172)
KA_RP = {"pattern": r"(?P<index>SOFR|Prime|Federal Funds)(?:\([A-Z]\))?\s*\+\s*(?P<spread_pct>\d+(?:\.\d+)?)\s*%", "spread_unit": "percent", "index_aliases": {"SOFR": "SOFR", "Prime": "Prime", "Federal Funds": "Federal Funds Effective Swap Rate"}}
TEMPLATES["1747172"] = (base(
    "1747172", "Kayne Anderson BDC, Inc.", "kayne-anderson-bdc-2026-layout-v1", "2026-03-31",
    "Typed labels: 'Debt Investments - {Industry} - {Issuer} - {Description} - Interest Rate 9.14% - Spread 5.50% - Reference SOFR(M) - Maturity Date M/D/YYYY'. HTML SOI is stated in thousands although no caption says so (XBRL/HTML value ratio ~1000): 'Portfolio Company | Footnotes | Investment | Interest Rate | Spread | PIK Rate | Reference | Maturity Date | Principal/ Par | Amortized Cost | Fair Value | Percentage of Net Assets' with industry heading rows; reference cells like 'SOFR(M)' / 'SOFR(Q)'.",
    ["0001193125-26-342385 (2026-06-30): 336 typed members; undimensioned fair value 2,291,802,000 and cost 2,304,505,000; HTML holding values are 1/1000 of matching XBRL facts (median ratio 588 before scaling) => fixed scale 1000",
     "0001193125-26-342385: InvestmentVariableInterestRateTypeExtensibleEnumeration values SOFR 280, Federal Funds Effective Swap Rate 6, Prime 3; HTML 'Amortized Cost' column corresponds to us-gaap:InvestmentOwnedAtCost",
     "0001193125-26-216773 (2026-03-31) inspected as the prior period"],
    html={"header_aliases": {"issuer_name": ["^Portfolio Company"], "security_description": ["^Investment"], "interest_rate": ["^Interest Rate"], "spread": ["^Spread"], "pik_rate": ["^PIK Rate"], "reference_index": ["^Reference"], "cost": ["^Amortized Cost", "^Cost$"], "fair_value": ["^Fair Value"], "maturity_date": ["^Maturity Date"], "principal_amount": ["^Principal"], "shares": ["^Number of Shares"], "footnote_markers": ["^Footnotes"]},
          "scale": {"source": "fixed", "fixed_multiplier": 1000, "default": 1000},
          "row_rules": {"carry_forward": [], "group_heading_target": "industry", "group_heading_rules": [{"regex": "affiliated|controlled", "target": "affiliate_status"}, {"regex": "^(Debt|Equity) Investments", "target": "investment_type"}], "total_if_regex": ["^Total Investments\\b(?!\\s+in\\s)"], "subtotal_if_regex": ["^Total\\b"], "require_any_numeric": ["fair_value", "cost", "principal_amount", "shares"]},
          "rate_parser": KA_RP, "prefer_html_fields": ["issuer_name"]},
    composite_fields=[{"id": "kayne-dash-label-v1", "source_field": "issuer_name", "applies_to": "xbrl",
                       "pattern": r"^(?P<investment_type>[^-]+?) - (?P<industry>.+?) - (?P<issuer>.+?) - (?P<description>.+?)(?: - Interest Rate (?P<interest_rate>\d+(?:\.\d+)?%))?(?: - Spread (?P<spread>\d+(?:\.\d+)?%))?(?: - Reference (?P<reference_index>[A-Za-z ]+?)(?:\([A-Z]\))?)?(?: - Maturity Date (?P<maturity>" + DATE + r"))?(?: - Acquisition Date .*)?$",
                       "rate_parser": KA_RP}],
    normalization={"legal_suffixes": {"remove_preceding_comma": True}, "date_formats": ["%m/%d/%Y", "%Y-%m-%d"], "spread_input_unit": "percent", "spread_output_format": "decimal", "reference_index_aliases": {"SOFR": "SOFR", "Prime": "Prime"}},
    validation={"allow_negative_fair_value": True, "allow_negative_fair_value_evidence": "0001193125-26-342385: 3 negative InvestmentOwnedAtFairValue facts on unfunded facilities."},
), hdr("Kayne Anderson BDC, Inc.", "1747172", "0001193125-26-342385", "2026-06-30"))

# ---------------------------------------------------------------- Muzinich BDC (1779523)
MUZ_RP = {"pattern": r"(?:\d+\s*Month\s+)?(?P<index>SOFR|Prime)(?:\s+USD)?\s*\+\s*(?P<spread_pct>\d+(?:\.\d+)?)\s*%", "spread_unit": "percent", "index_aliases": {"SOFR": "SOFR", "Prime": "Prime"}}
TEMPLATES["1779523"] = (base(
    "1779523", "Muzinich BDC, Inc.", "muzinich-bdc-2026-layout-v1", "2026-03-31",
    "Typed members form a hierarchy ('Senior Secured Loan Debt Investments - {Industry} - {Issuer} - {Description}', 'Equity Investments - Common Stock - {Industry} - {Issuer} - {Description}') whose parent nodes aggregate children; 'Net Assets'/'Liabilities in Excess of Other Assets' are also members. HTML SOI is in whole dollars although the statements heading says thousands: 'Portfolio Company | Footnotes | Security | Spread Above Index | Floor | Interest Rate/Discount Rate | Payment-in-Kind Interest Rate | Acquisition Dates | Maturity/Expiration Date | Principal / Units | Amortized Cost | Fair Value | Percentage of Net Assets'; grand total 'Total Investments $236,305,097 $214,085,177'. The undimensioned XBRL InvestmentOwnedAtFairValue/AtCost facts are not the SOI totals in this filing.",
    ["0001213900-26-089024 (2026-06-30): HTML holding amounts (e.g. $10,676,203) equal XBRL facts in whole dollars (median ratio 0.001 when scaled by 1000) => fixed scale 1",
     "0001213900-26-089024: HTML 'Total Investments $236,305,097 $214,085,177' is the SOI grand total; the undimensioned XBRL facts (amortized cost 19,500,000; fair value 0.023) do not represent it => total_source_preference html_template_total",
     "0001213900-25-056043 (2026-03-31) inspected as the prior period"],
    xbrl={"role_regex": ["Schedule of Investments"], "row_axes": {"explicit_qnames": ["us-gaap:InvestmentIdentifierAxis"], "exclude_regex": ["FairValue.*Hierarchy"],
                                                             "exclude_member_regex": [r"^(?!(?:Senior Secured Loan Debt Investments|Debt Investments|Subordinated Debt Investments|Unsecured Debt Investments) - [^-]+ - .+ - [^-]+$)(?!Equity Investments - [^-]+ - [^-]+ - .+ - [^-]+$)"],
                                                             "exclude_member_evidence": "0001213900-26-089024: the holding axis is a hierarchy; section nodes ('Senior Secured Loan Debt Investments - Industrial Machinery', 'Equity Investments - Common Stock - Automotive', 'Investments', 'Net Assets') aggregate their children; only leaf labels of the shape 'Section - Industry - Issuer - Description' (debt) or 'Equity Investments - Class - Industry - Issuer - Description' (equity) are holdings; hybrid leaf rows sum to the HTML total 214,085,177."},
          "context_filters": {"require_report_date": True, "allowed_period_types": ["instant"], "excluded_axes_regex": ["FairValueByFairValueHierarchyLevel"]},
          "total_concepts": {}},
    html={"header_aliases": {"issuer_name": ["^Portfolio Company"], "security_description": ["^Security"], "interest_rate_text": ["^Spread Above Index"], "rate_floor": ["^Floor"], "interest_rate": ["^Interest Rate/Discount Rate", "^Interest Rate"], "pik_rate": ["^Payment-in-Kind"], "cost": ["^Amortized Cost"], "fair_value": ["^Fair Value"], "maturity_date": ["^Maturity/Expiration Date"], "footnote_markers": ["^Footnotes"]},
          "scale": {"source": "fixed", "fixed_multiplier": 1, "default": 1},
          "row_rules": {"carry_forward": [], "group_heading_target": "industry", "group_heading_rules": [{"regex": "affiliated|controlled", "target": "affiliate_status"}, {"regex": "Debt Investments|Equity Investments|Preferred Stock|Common Stock", "target": "investment_type"}], "total_if_regex": ["^Total Investments\\b(?!\\s+in\\s)"], "subtotal_if_regex": ["^Total\\b"], "require_any_numeric": ["fair_value", "cost", "principal_amount", "shares"]},
          "rate_parser": MUZ_RP, "prefer_html_fields": ["issuer_name"]},
    composite_fields=[{"id": "muzinich-debt-label-v1", "source_field": "issuer_name", "applies_to": "xbrl", "pattern": r"^(?P<investment_type>Senior Secured Loan Debt Investments|Debt Investments|Subordinated Debt Investments) - (?P<industry>[^-]+?) - (?P<issuer>.+?) - (?P<description>[^-]+)$"},
                      {"id": "muzinich-equity-label-v1", "source_field": "issuer_name", "applies_to": "xbrl", "pattern": r"^(?P<investment_type>Equity Investments) - (?P<security>[^-]+?) - (?P<industry>[^-]+?) - (?P<issuer>.+?) - (?P<description>[^-]+)$", "capture_targets": {"security": "sector"}}],
    normalization={"legal_suffixes": {"remove_preceding_comma": True}, "date_formats": ["%m/%d/%Y", "%Y-%m-%d"], "spread_input_unit": "percent", "spread_output_format": "decimal", "reference_index_aliases": {}},
    validation={"total_source_preference": ["html_template_total", "xbrl_no_dimensions"], "total_source_preference_evidence": "0001213900-26-089024: HTML 'Total Investments $236,305,097 $214,085,177' equals the sum of HTML holding rows; the undimensioned us-gaap:InvestmentOwnedAtFairValue/AtCost facts carry unrelated values (0.023 / 19,500,000)."},
), hdr("Muzinich BDC, Inc.", "1779523", "0001213900-26-089024", "2026-06-30"))

# ---------------------------------------------------------------- New Mountain Guardian IV BDC (1925531)
NMG_RP = {"pattern": r"(?P<index>SOFR|Prime|EURIBOR|SONIA)(?:\([A-Z]\))?\s*\+\s*(?P<spread_pct>\d+(?:\.\d+)?)\s*%", "spread_unit": "percent", "index_aliases": {"SOFR": "SOFR", "Prime": "Prime", "EURIBOR": "EURIBOR", "SONIA": "SONIA"}}
TEMPLATES["1925531"] = (base(
    "1925531", "New Mountain Guardian IV BDC, L.L.C.", "new-mountain-guardian-iv-2026-layout-v1", "2026-03-31",
    "Typed labels 'Issuer | Description' (e.g. 'AAH Topco, LLC | First Lien - Drawn'). HTML SOI in thousands: 'Portfolio Company, Location and Industry | Type of Investment | Reference | Spread | Interest Rate | Purchase Date | Maturity/Expiration Date | Principal Amount, Par Value or Shares | Cost | Fair Value | Percent of Net Assets'; the issuer is a heading row and the first column of the first facility row carries the location/industry text; maturities are MM/YYYY (left null).",
    ["0001925531-26-000014 (2026-06-30): 445 typed members; undimensioned fair value 2,071,442,000 and cost 2,095,505,000 within tolerance of the holdings sums",
     "0001925531-26-000014: reference cells 'SOFR(Q)' / 'SOFR(M)'; 92 negative fair-value facts on undrawn facilities",
     "0001925531-26-000010 (2026-03-31) inspected as the prior period"],
    html={"header_aliases": {"industry": ["^Portfolio Company, Location and Industry"], "security_description": ["^Type of Investment"], "reference_index": ["^Reference"], "spread": ["^Spread"], "interest_rate": ["^Interest Rate"], "cost": ["^Cost"], "fair_value": ["^Fair Value"], "maturity_date": ["^Maturity"], "principal_amount": ["^Principal Amount"]},
          "row_rules": {"carry_forward": [], "group_heading_target": "issuer_name", "group_heading_rules": [{"regex": "affiliated|controlled", "target": "affiliate_status"}], "total_if_regex": ["^Total Investments\\b(?!\\s+in\\s)", "^Total investments\\b(?!\\s+in\\s)"], "subtotal_if_regex": ["^Total\\b"], "require_any_numeric": ["fair_value", "cost", "principal_amount", "shares"]},
          "rate_parser": NMG_RP, "prefer_html_fields": []},
    composite_fields=[{"id": "nmg4-pipe-label-v1", "source_field": "issuer_name", "applies_to": "xbrl", "kind": "delimited", "delimiter": "|", "positions": {"issuer": 0, "description": 1}, "min_parts": 2}],
    normalization={"legal_suffixes": {"remove_preceding_comma": True}, "date_formats": ["%m/%d/%Y", "%Y-%m-%d"], "spread_input_unit": "percent", "spread_output_format": "decimal", "reference_index_aliases": {"SOFR": "SOFR"}},
    validation={"allow_negative_fair_value": True, "allow_negative_fair_value_evidence": "0001925531-26-000014: 92 negative InvestmentOwnedAtFairValue facts on undrawn/unfunded facilities."},
), hdr("New Mountain Guardian IV BDC, L.L.C.", "1925531", "0001925531-26-000014", "2026-06-30"))

# ---------------------------------------------------------------- Onex Direct Lending BDC Fund (1860424)
onex_ind = html_industry_headings("1860424")
ONEX_RP = {"pattern": r"(?:\d+M\s+)?(?P<index>SOFR|Prime|FFR)\s*\+\s*(?P<spread_pct>\d+(?:\.\d+)?)\s*%", "spread_unit": "percent", "index_aliases": {"SOFR": "SOFR", "Prime": "Prime", "FFR": "Federal Funds Rate"}}
TEMPLATES["1860424"] = (base(
    "1860424", "Onex Direct Lending BDC Fund", "onex-direct-lending-2026-layout-v1", "2026-03-31",
    "Typed labels: '{Affiliation} {Debt Investments|Equity} [{Affiliation} {Section}] {Industry} {Issuer} {Description} Reference Rate and Spread 3M SOFR + 5.25% Floor 0.50% Interest Rate 9.01% Initial Acquisition Date M/D/YYYY Maturity Date M/D/YYYY'. HTML SOI in whole dollars: 'Portfolio Company | Investment Type | Reference Rate and Spread | Floor | Interest Rate | Initial Acquisition Date | Maturity Date | Par/Shares | Amortized Cost | Fair Value | % of Net Assets | Footnotes' with industry headings; 'Liabilities in Excess of Other Assets' rows are not holdings.",
    ["0001193125-26-339194 (2026-06-30): 100 typed members (25 without monetary facts); undimensioned fair value 287,774,870 equals the XBRL holdings sum; cost 323,273,856 equals",
     "0001193125-26-339194: HTML 'Amortized Cost' equals us-gaap:InvestmentOwnedAtCost on 70/70 matched rows => cost; 12 negative fair-value facts on unfunded facilities; industry vocabulary from HTML heading rows",
     "0001193125-26-213421 (2026-03-31) inspected as the prior period"],
    html={"header_aliases": {"issuer_name": ["^Portfolio Company"], "security_description": ["^Investment Type"], "interest_rate_text": ["^Reference Rate and Spread"], "rate_floor": ["^Floor"], "interest_rate": ["^Interest Rate"], "cost": ["^Amortized Cost"], "fair_value": ["^Fair Value"], "maturity_date": ["^Maturity Date"], "footnote_markers": ["^Footnotes"]},
          "scale": {"source": "fixed", "fixed_multiplier": 1, "default": 1},
          "row_rules": {"carry_forward": [], "group_heading_target": "industry", "group_heading_rules": [{"regex": "affiliated|controlled", "target": "affiliate_status"}, {"regex": "^(Debt Investments|Equity)$", "target": "investment_type"}], "skip_if_regex": ["^Liabilities in Excess", "^Net Assets"], "total_if_regex": ["^Total Investments\\b(?!\\s+in\\s)"], "subtotal_if_regex": ["^Total\\b"], "require_any_numeric": ["fair_value", "cost", "principal_amount", "shares"]},
          "rate_parser": ONEX_RP, "prefer_html_fields": ["issuer_name"]},
    composite_fields=[{"id": "onex-label-v1", "source_field": "issuer_name", "applies_to": "xbrl",
                       "pattern": r"^(?P<affiliate_status>Non-controlled/Non-affiliated investments|Non-controlled/Affiliated investments|Controlled/Affiliated investments)\s+(?P<investment_type>Debt Investments|Equity)\s+(?:(?P=affiliate_status)\s+(?P=investment_type)\s+)?(?P<header>.+?)(?:\s+Reference Rate and Spread\s+(?P<rate>.+?))?(?:\s+Floor\s+(?P<rate_floor>\d+(?:\.\d+)?%))?(?:\s+Interest Rate\s+(?P<interest_rate>\d+(?:\.\d+)?%))?(?:\s+Initial Acquisition Date\s+" + DATE + r")?(?:\s+Maturity Date\s+(?P<maturity>" + DATE + r"))?$",
                       "header_parser": {"known_industries": onex_ind, "industry_position": "prefix", "remainder_target": "issuer_name"}, "rate_parser": ONEX_RP}],
    normalization={"legal_suffixes": {"remove_preceding_comma": True}, "date_formats": ["%m/%d/%Y", "%Y-%m-%d"], "spread_input_unit": "percent", "spread_output_format": "decimal", "reference_index_aliases": {"SOFR": "SOFR"}},
    validation={"allow_negative_fair_value": True, "allow_negative_fair_value_evidence": "0001193125-26-339194: 12 negative InvestmentOwnedAtFairValue facts on unfunded revolver/delayed-draw facilities."},
), hdr("Onex Direct Lending BDC Fund", "1860424", "0001193125-26-339194", "2026-06-30"))

# ---------------------------------------------------------------- PIMCO Capital Solutions BDC (1905824)
PIMCO_RP = {"pattern": r"(?P<index>SOFR|EURIBOR|Prime)\s*\+\s*(?P<spread_pct>\d+(?:\.\d+)?)\s*%", "spread_unit": "percent", "pik_pattern": r"\(\s*(?P<pik_pct>\d+(?:\.\d+)?)\s*%\s*PIK\s*\)", "index_aliases": {"SOFR": "SOFR", "EURIBOR": "EURIBOR", "Prime": "Prime"}}
TEMPLATES["1905824"] = (base(
    "1905824", "PIMCO Capital Solutions BDC Corp.", "pimco-capital-solutions-2026-layout-v1", "2026-03-31",
    "Typed labels are pipe-delimited: 'Debt Investments | First Lien Senior Secured | Technology | MRI Software, LLC Term Loan | SOFR + 4.750 % | 8.450 % | 02/10/2028' (issuer and facility share one part, as in the HTML 'Investments' column); a 'Total Investments' member is tagged on the holding axis. HTML SOI in thousands: 'Investments | Reference Rate Spread | Interest Rate | Maturity Date | Par Amount/ Shares | Cost | Fair Value | Percentage of Net Assets'.",
    ["0001193125-26-344935 (2026-06-30): 93 typed members incl. 'Total Investments' (197,727,000) which equals the undimensioned InvestmentOwnedAtFairValue; HTML 'Total Investments $202,599 $197,727'",
     "0001193125-26-344935: SOFR appears as the full word in labels and HTML; rates like '20.000% PIK' and '17.000% ( 7.000% PIK)'",
     "0001193125-26-224212 (2026-03-31) inspected as the prior period"],
    html={"header_aliases": {"issuer_name": ["^Investments"], "interest_rate_text": ["^Reference Rate Spread"], "interest_rate": ["^Interest Rate"], "cost": ["^Cost"], "fair_value": ["^Fair Value"], "maturity_date": ["^Maturity Date"]},
          "row_rules": {"carry_forward": [], "group_heading_target": "industry", "group_heading_rules": [{"regex": "affiliated|controlled", "target": "affiliate_status"}, {"regex": "^(Debt Investments|Equity Investments|Short-Term Investments)$", "target": "investment_type"}, {"regex": "^(First Lien Senior Secured|Second Lien Senior Secured|Unsecured|Warrants|Common Stock|Preferred Stock|U\\.S\\. Treasury Bills|U\\.S\\. Government Agencies)$", "target": "sector"}], "total_if_regex": ["^Total Investments\\b(?!\\s+in\\s)"], "subtotal_if_regex": ["^Total\\b"], "require_any_numeric": ["fair_value", "cost", "principal_amount", "shares"]},
          "rate_parser": PIMCO_RP, "prefer_html_fields": ["issuer_name"]},
    composite_fields=[{"id": "pimco-pipe-label-v1", "source_field": "issuer_name", "applies_to": "xbrl",
                       "pattern": r"^(?P<investment_type>[^|]+?)\s*\|\s*(?P<security>[^|]+?)\s*\|\s*(?P<industry>[^|]+?)\s*\|\s*(?P<issuer>[^|]+?)\s*(?:\|\s*(?P<rate>[^|]*?\+[^|]*?)\s*)?(?:\|\s*(?P<interest_rate>\d+(?:\.\d+)?\s*%)\s*)?(?:\|\s*(?P<maturity>" + DATE + r")\s*)?$",
                       "capture_targets": {"security": "sector"}, "rate_parser": PIMCO_RP}],
    normalization={"legal_suffixes": {"remove_preceding_comma": True}, "date_formats": ["%m/%d/%Y", "%Y-%m-%d"], "spread_input_unit": "percent", "spread_output_format": "decimal", "reference_index_aliases": {}},
), hdr("PIMCO Capital Solutions BDC Corp.", "1905824", "0001193125-26-344935", "2026-06-30"))

# ---------------------------------------------------------------- Palmer Square Capital BDC (1794776)
ps_ind = html_industry_headings("1794776")
PS_RP = {"pattern": r"\(\s*(?P<index>S|P|SOFR|Prime)\s*\+\s*(?:CSA\s*\+\s*)?(?P<spread_pct>\d+(?:\.\d+)?)\s*%\s*\)", "interest_rate_pattern": r"^(?P<rate_pct>\d+(?:\.\d+)?)\s*%", "spread_unit": "percent", "index_aliases": {"S": "SOFR", "SOFR": "SOFR", "P": "Prime", "Prime": "Prime"}}
TEMPLATES["1794776"] = (base(
    "1794776", "Palmer Square Capital BDC Inc.", "palmer-square-2026-layout-v1", "2026-03-31",
    "Typed labels: 'Portfolio Company {Section} {Industry} {Issuer} Investment {Description} Interest Rate 6.60% (S + 2.75%) Maturity Date M/D/YYYY'. HTML SOI in whole dollars: 'Portfolio Company | Investment | Interest Rate | Maturity Date | Principal / Par | Amortized Cost | Fair Value | Percentage of Net Assets' with industry headings; rate text '6.60% (S + 2.75%)' / '7.51% (S +CSA + 3.75%)'.",
    ["0001193125-26-333791 (2026-06-30): 319 typed members; undimensioned fair value 1,113,377,240 and cost 1,242,154,553 within tolerance of the holdings sums; HTML 'Amortized Cost' equals us-gaap:InvestmentOwnedAtCost on 263/263 matched rows",
     "0001193125-26-333791: 'S' supported by InvestmentVariableInterestRateTypeExtensibleEnumeration = SOFR on 253 members; industry vocabulary from HTML heading rows",
     "0001193125-26-207523 (2026-03-31) inspected as the prior period"],
    html={"header_aliases": {"issuer_name": ["^Portfolio Company"], "security_description": ["^Investment$"], "interest_rate_text": ["^Interest Rate"], "cost": ["^Amortized Cost", "^Cost$"], "fair_value": ["^Fair Value"], "maturity_date": ["^Maturity Date"], "principal_amount": ["^Principal"], "shares": ["^Number of Shares"]},
          "scale": {"source": "fixed", "fixed_multiplier": 1, "default": 1},
          "row_rules": {"carry_forward": [], "group_heading_target": "industry", "group_heading_rules": [{"regex": "affiliated|controlled", "target": "affiliate_status"}, {"regex": "^(Debt Investments|Equity Investments|Structured Subordinated Note|Collateralized Loan Obligations?)$", "target": "investment_type"}], "total_if_regex": ["^Total Investments\\b(?!\\s+in\\s)"], "subtotal_if_regex": ["^Total\\b"], "require_any_numeric": ["fair_value", "cost", "principal_amount", "shares"]},
          "rate_parser": PS_RP, "prefer_html_fields": ["issuer_name"]},
    composite_fields=[{"id": "palmer-square-label-v1", "source_field": "issuer_name", "applies_to": "xbrl",
                       "pattern": r"^Portfolio Company\s+(?P<investment_type>Debt Investments|Equity Investments|Structured Subordinated Note|Structured Subordinated Notes)\s+(?P<header>.+?)\s+Investment\s+(?P<description>.+?)(?:\s+Interest Rate\s+(?P<rate>.+?))?(?:\s+Maturity Date\s+(?P<maturity>" + DATE + r"))?$",
                       "header_parser": {"known_industries": ps_ind, "industry_position": "prefix", "remainder_target": "issuer_name"}, "rate_parser": PS_RP}],
    normalization={"legal_suffixes": {"remove_preceding_comma": True}, "date_formats": ["%m/%d/%Y", "%Y-%m-%d"], "spread_input_unit": "percent", "spread_output_format": "decimal", "reference_index_aliases": {"S": "SOFR", "P": "Prime"}},
), hdr("Palmer Square Capital BDC Inc.", "1794776", "0001193125-26-333791", "2026-06-30"))
