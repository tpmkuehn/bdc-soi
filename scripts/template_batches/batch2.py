"""Batch 2 templates: Franklin BSP Real Estate Debt BDC, Golub Capital BDC, Goldman Sachs BDC, Golub Capital BDC 4,
Investcorp Credit Management BDC, Jefferies Credit Partners BDC."""

from template_batches.batch1 import DATE, base, hdr  # type: ignore
from write_templates import html_industry_headings  # type: ignore

TEMPLATES = {}

GOLUB_RP = {"pattern": r"(?P<index>SF|E|P|SN|A|CA|SOFR|EURIBOR|Prime|SONIA|CORRA)\s*\+\s*(?P<spread_pct>\d+(?:\.\d+)?)\s*%", "spread_unit": "percent",
            "index_aliases": {"SF": "SOFR", "SOFR": "SOFR", "E": "EURIBOR", "EURIBOR": "EURIBOR", "P": "Prime", "Prime": "Prime", "SN": "SONIA", "SONIA": "SONIA", "A": "AUD Interbank", "CA": "CORRA", "CORRA": "CORRA"}}
GOLUB_LEGEND = "HTML footnote (1): 'Secured Overnight Financing Rate (SOFR or SF), Euro Interbank Offered Rate (EURIBOR or E), Prime (P), Sterling Overnight Index Average (SONIA or SN), Australian Interbank Rate (AUD or A) or Canadian Overnight Repo Rate Average (CORRA or CA)'"

# ---------------------------------------------------------------- Franklin BSP Real Estate Debt BDC (2018545)
TEMPLATES["2018545"] = (base(
    "2018545", "Franklin BSP Real Estate Debt BDC", "franklin-bsp-red-2025-layout-v1", "2025-03-31",
    "Real-estate debt BDC. Typed labels '{Borrower}, {Property type}' (Multifamily, Industrial, Hospitality, Mixed Use, Self Storage). HTML SOI in thousands: 'Portfolio Company | Spread Above Reference Rate | Interest Rate | Maturity Date | Par Amount | Amortized Cost | Fair Value | % of Net Assets' with headings 'Senior Mortgage - 219.7%' / 'Mezzanine - 4.6%' and property-type headings. Latest eligible 10-Q is 2025-06-30 (no later 10-Q filed within the lookback as of 2026-10-06).",
    ["0002018545-25-000016 (2025-06-30): 89 typed members (24 without monetary facts); undimensioned fair value 1,275,931,000 and cost 1,266,301,000 within tolerance of the holdings sums",
     "0002018545-25-000016: HTML 'Amortized Cost' equals us-gaap:InvestmentOwnedAtCost on 54/54 matched rows => cost; only SOFR appears in rate text",
     "0002018545-25-000011 (2025-03-31) inspected as the prior period"],
    html={"header_aliases": {"issuer_name": ["^Portfolio Company"], "interest_rate_text": ["^Spread Above Reference Rate"], "interest_rate": ["^Interest Rate"], "cost": ["^Amortized Cost"], "fair_value": ["^Fair Value"], "maturity_date": ["^Maturity Date"], "principal_amount": ["^Par Amount"]},
          "row_rules": {"carry_forward": [], "group_heading_target": "industry", "group_heading_rules": [{"regex": "^(Senior Mortgage|Mezzanine|Subordinate|Preferred Equity)", "target": "investment_type"}], "total_if_regex": ["^Total Investments\\b(?!\\s+in\\s)"], "subtotal_if_regex": ["^(?:Sub)?[Tt]otal\\b"], "require_any_numeric": ["fair_value", "cost", "principal_amount"]},
          "prefer_html_fields": ["issuer_name"]},
    composite_fields=[{"id": "fbred-label-v1", "source_field": "issuer_name", "applies_to": "xbrl", "pattern": r"^(?P<issuer>.+), (?P<industry>Multifamily|Industrial|Hospitality|Mixed Use|Self Storage|Office|Retail|Land|Other)$"}],
    normalization={"legal_suffixes": {"remove_preceding_comma": True}, "date_formats": ["%m/%d/%Y", "%Y-%m-%d"], "spread_input_unit": "percent", "spread_output_format": "decimal", "reference_index_aliases": {}},
), hdr("Franklin BSP Real Estate Debt BDC", "2018545", "0002018545-25-000016", "2025-06-30"))

# ---------------------------------------------------------------- Golub Capital BDC (1476765) and Golub Capital BDC 4 (1901612)
for cik, name, tid, acc, prior, members in (("1476765", "GOLUB CAPITAL BDC, Inc.", "golub-capital-bdc-2026-layout-v1", "0001476765-26-000048", "0001476765-26-000033", "1,812 typed members 'Issuer | One stop 2 | Non-Affiliated Issuer'"),
                                             ("1901612", "Golub Capital BDC 4, Inc.", "golub-capital-bdc4-2026-layout-v1", "0001901612-26-000031", "0001901612-26-000020", "922 typed members 'Issuer | One stop 1'")):
    TEMPLATES[cik] = (base(
        cik, name, tid, "2026-03-31",
        "Typed labels are pipe-delimited 'Issuer | Description [| Affiliation]'. HTML SOI in thousands with an unnamed first column (issuer), 'Investment Type', a split 'Spread Above Index' column ('SF +' / '5.50%'), 'Interest Rate', 'Maturity Date' (MM/YYYY only, left null), 'Principal ($) / Shares', 'Amortized Cost', 'Percentage of Net Assets', 'Fair Value'; industry heading rows; no maturity-date XBRL facts.",
        [f"{acc} (2026-06-30): {members}; HTML 'Amortized Cost' equals us-gaap:InvestmentOwnedAtCost on all matched rows => cost",
         f"{acc}: {GOLUB_LEGEND}; industry vocabulary from the filing's HTML heading rows",
         f"{acc}: negative fair-value facts on unfunded facilities (one stop revolvers/delayed draws)",
         f"{prior} (2026-03-31) inspected as the prior period"],
        html={"header_aliases": {"security_description": ["^Investment Type"], "interest_rate_text": ["^Spread Above Index"], "interest_rate": ["^Interest Rate"], "cost": ["^Amortized Cost"], "fair_value": ["^Fair Value"], "maturity_date": ["^Maturity Date"]},
              "row_rules": {"carry_forward": ["issuer_name"], "group_heading_target": "industry", "known_industries": html_industry_headings(cik), "group_heading_rules": [{"regex": "affiliate|control", "target": "affiliate_status"}, {"regex": "^(Debt|Equity) investments", "target": "investment_type"}], "total_if_regex": ["^Total investments\\b(?!\\s+in\\s)", "^Total Investments\\b(?!\\s+in\\s)"], "subtotal_if_regex": ["^(?:Sub)?[Tt]otal\\b"], "require_any_numeric": ["fair_value", "cost", "principal_amount", "shares"]},
              "rate_parser": GOLUB_RP, "prefer_html_fields": ["issuer_name"]},
        composite_fields=[{"id": "golub-pipe-label-v1", "source_field": "issuer_name", "applies_to": "xbrl", "kind": "delimited", "delimiter": "|", "positions": {"issuer": 0, "description": 1, "affiliate_status": 2}, "min_parts": 2}],
        normalization={"legal_suffixes": {"remove_preceding_comma": True}, "date_formats": ["%m/%d/%Y", "%Y-%m-%d"], "spread_input_unit": "percent", "spread_output_format": "decimal", "reference_index_aliases": {"SF": "SOFR", "E": "EURIBOR", "P": "Prime", "SN": "SONIA", "A": "AUD Interbank", "CA": "CORRA"}},
        validation={"allow_negative_fair_value": True, "allow_negative_fair_value_evidence": f"{acc}: negative InvestmentOwnedAtFairValue facts on unfunded revolver/delayed-draw members (HTML '(2)' style)."},
    ), hdr(name, cik, acc, "2026-06-30"))

# ---------------------------------------------------------------- Goldman Sachs BDC (1572694)
GS_RP = {"pattern": r"(?P<index>S|C|E|P|SN|B|N|SOFR|CORRA|EURIBOR|Prime|SONIA)\s*\+\s*(?P<spread_pct>\d+(?:\.\d+)?)\s*%", "spread_unit": "percent", "pik_pattern": r"(?P<pik_pct>\d+(?:\.\d+)?)\s*%\s*PIK",
         "index_aliases": {"S": "SOFR", "SOFR": "SOFR", "C": "CORRA", "CORRA": "CORRA", "E": "EURIBOR", "EURIBOR": "EURIBOR", "P": "Prime", "Prime": "Prime", "SN": "SONIA", "SONIA": "SONIA", "B": "BBSY", "N": "NIBOR"}}
TEMPLATES["1572694"] = (base(
    "1572694", "Goldman Sachs BDC, Inc.", "goldman-sachs-bdc-2026-layout-v1", "2026-03-31",
    "Typed labels: 'Investment {Section} - x% {Country} - x% {Security type} - x% {Issuer} Industry {Industry} Interest Rate 8.41% Reference Rate and Spread S + 4.75% Maturity MM/DD/YY [Acquisition Date ...]'. HTML SOI in thousands: 'Investment | Industry | Interest Rate | Reference Rate and Spread | Maturity | Par | Cost | Fair Value | Footnotes' with section/country/security-type heading rows carrying percentages; foreign-currency par shown as 'CAD 7,791'.",
    ["0001193125-26-338331 (2026-06-30): 560 typed members; undimensioned fair value 3,195,248,000 and cost 3,410,976,000 within tolerance of the holdings sums",
     "0001193125-26-338331: index letters S/C/E/P/SN/B/N supported by InvestmentVariableInterestRateTypeExtensibleEnumeration (SOFR 494, CORRA 9, Prime 5) on the same members; 5 fair-value facts tagged in CAD equal the USD HTML cells (reporting-currency confirmation rule)",
     "0001193125-26-338331: 117 negative fair-value facts on unfunded facilities; maturities are MM/DD/YY",
     "0001193125-26-212431 (2026-03-31) inspected as the prior period"],
    html={"header_aliases": {"issuer_name": ["^Investment"], "industry": ["^Industry"], "interest_rate": ["^Interest Rate"], "interest_rate_text": ["^Reference Rate and Spread"], "cost": ["^Cost"], "fair_value": ["^Fair Value"], "maturity_date": ["^Maturity"], "principal_amount": ["^Par"], "footnote_markers": ["^Footnotes"]},
          "row_rules": {"carry_forward": [], "group_heading_target": "investment_type", "group_heading_rules": [{"regex": "affiliated|controlled", "target": "affiliate_status"}, {"regex": "^(United States|Canada|United Kingdom|India|Australia|Europe|Netherlands|Germany|France|Luxembourg|Ireland|Spain|Sweden|Norway|Denmark|Belgium|Italy|Switzerland|Israel|Singapore|Japan)\\b", "target": "country"}], "total_if_regex": ["^Total Investments\\b(?!\\s+in\\s)", "^Total investments\\b(?!\\s+in\\s)"], "subtotal_if_regex": ["^Total\\b"], "require_any_numeric": ["fair_value", "cost", "principal_amount", "shares"]},
          "rate_parser": GS_RP, "prefer_html_fields": ["issuer_name"]},
    composite_fields=[{"id": "gsbd-label-v1", "source_field": "issuer_name", "applies_to": "xbrl",
                       "pattern": r"^Investment\s+(?P<investment_type>.+?) [-–] \d+(?:\.\d+)?%\s+(?P<country>.+?) [-–] \d+(?:\.\d+)?%\s+(?P<security>.+?) [-–] \d+(?:\.\d+)?%\s+(?P<issuer>.+?)\s+Industry\s+(?P<industry>.+?)(?:\s+Interest Rate\s+(?P<interest_rate>\d+(?:\.\d+)?%))?(?:\s+Reference Rate and Spread\s+(?P<rate>.+?))?(?:\s+Maturity\s+(?P<maturity>\d{2}/\d{2}/\d{2}))?(?:\s+Acquisition Date.*)?$",
                       "capture_targets": {"security": "description"}, "rate_parser": GS_RP}],
    normalization={"legal_suffixes": {"remove_preceding_comma": True}, "date_formats": ["%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"], "spread_input_unit": "percent", "spread_output_format": "decimal", "reference_index_aliases": {"S": "SOFR", "C": "CORRA", "E": "EURIBOR", "P": "Prime", "SN": "SONIA"}},
    validation={"reporting_currency_evidence": ['0001193125-26-338331 and 0001193125-26-212431, Consolidated Schedule of Investments footnote: \'Par amount is denominated in U.S. Dollars ("$" or "USD") unless otherwise noted, Euros ("EUR"), Great British Pounds ("GBP"), Norwegian Kroner ("NOK"), Canadian Dollars ("CAD") or Australian Dollars ("AUD").\'', "0001193125-26-338331 and 0001193125-26-212431, Note 2 Basis of Presentation: 'The Company's functional currency is USD and these consolidated financial statements have been prepared in that currency.' and 'purchases and sales of investments ... denominated in foreign currencies are translated into USD based upon currency exchange rates prevailing on the transaction dates.'"], "allow_negative_fair_value": True, "allow_negative_fair_value_evidence": "0001193125-26-338331: 117 negative InvestmentOwnedAtFairValue facts on unfunded facilities."},
), hdr("Goldman Sachs BDC, Inc.", "1572694", "0001193125-26-338331", "2026-06-30"))

# ---------------------------------------------------------------- Investcorp Credit Management BDC (1578348)
inv_ind = html_industry_headings("1578348")
INV_RP = {"pattern": r"(?:\d+M\s+)?(?P<index>S|SOFR|P|Prime)\s*\+\s*(?P<spread_pct>\d+(?:\.\d+)?)\s*%", "spread_unit": "percent", "floor_pattern": r"\((?P<floor_pct>\d+(?:\.\d+)?)\s*%\s*Floor\)", "pik_pattern": r"(?P<pik_pct>\d+(?:\.\d+)?)\s*%\s*PIK", "index_aliases": {"S": "SOFR", "SOFR": "SOFR", "P": "Prime", "Prime": "Prime"}}
TEMPLATES["1578348"] = (base(
    "1578348", "Investcorp Credit Management BDC, Inc.", "investcorp-cm-bdc-2026-layout-v1", "2026-03-31",
    "Typed labels: '{Affiliation}, {Section}, {Industry}, {Issuer} - {Description}[, Interest Rate ...][, Acquisition Date ...][, Maturity Date M/D/YYYY]'; section-node members (e.g. 'Investment in non-controlled, Affiliated Investments') aggregate their children. HTML SOI in whole dollars: 'Investments | Interest Rate | Maturity Date | Principal Amount/ Shares | Amortized Cost/ Cost | Fair Value | % of Net Assets' with affiliation and industry headings; rates like '1M S + 6.50% PIK (1.00% Floor)' and '10.00% PIK'.",
    ["0001193125-26-352658 (2026-06-30): 56 typed members incl. section nodes; undimensioned cost 161,157,365 equals the holdings sum; HTML 'Amortized Cost/ Cost' equals us-gaap:InvestmentOwnedAtCost on 38/38 matched rows",
     "0001193125-26-352658: 'S' supported by InvestmentVariableInterestRateTypeExtensibleEnumeration values 'Three Month Sofr'/'One Month Sofr' on the same members",
     "0001193125-26-220107 (2026-03-31) inspected as the prior period; industry vocabulary from HTML heading rows",
     "0001193125-26-352658 equity members: the section name 'Equity, Warrants and Other Investments' contains a comma and the label ends ', Initial Acquisition Date M/D/YYYY' (e.g. 'Non-Controlled/Non-Affiliated Investments, Equity, Warrants and Other Investments, Commercial Services & Supplies, ArborWorks, LLC B-1 - Preferred Units, Initial Acquisition Date 11/24/2021'); '{Issuer} - {Description}' is split inside the label; these members carry InvestmentOwnedBalanceShares facts and the HTML 'Investments' cell carries '{Issuer} - {Description}' with the share count in 'Principal Amount/ Shares' (table_10 rows 5-28)"],
    xbrl={"role_regex": ["Schedule of Investments"], "row_axes": {"explicit_qnames": ["us-gaap:InvestmentIdentifierAxis"], "exclude_regex": ["FairValue.*Hierarchy"], "exclude_member_regex": [r"^Investment in ", r"^Investments in ", r"^Total\b"], "exclude_member_evidence": "0001193125-26-352658: members 'Investment in non-controlled, Affiliated Investment' (9,514,365) and similar section aggregates equal the sums of the affiliation sections and are not holdings; excluding them leaves the XBRL sum equal to the undimensioned InvestmentOwnedAtFairValue 135,930,163."},
          "context_filters": {"require_report_date": True, "allowed_period_types": ["instant"], "excluded_axes_regex": ["FairValueByFairValueHierarchyLevel"]},
          "total_concepts": {"fair_value": ["us-gaap:InvestmentOwnedAtFairValue"], "cost": ["us-gaap:InvestmentOwnedAtCost"]}},
    html={"header_aliases": {"issuer_name": ["^Investments"], "interest_rate_text": ["^Interest Rate"], "cost": ["^Amortized Cost"], "fair_value": ["^Fair Value"], "maturity_date": ["^Maturity Date"]},
          "scale": {"source": "fixed", "fixed_multiplier": 1, "default": 1},
          "row_rules": {"carry_forward": [], "group_heading_target": "industry", "group_heading_rules": [{"regex": "affiliated|controlled", "target": "affiliate_status"}, {"regex": "Debt Investments|Equity|Warrants|Preferred", "target": "investment_type"}], "total_if_regex": ["^Total Investments\\b(?!\\s+in\\s)"], "subtotal_if_regex": ["^Total\\b"], "require_any_numeric": ["fair_value", "cost", "principal_amount", "shares"]},
          "rate_parser": INV_RP, "prefer_html_fields": ["issuer_name"]},
    composite_fields=[{"id": "investcorp-label-v1", "source_field": "issuer_name", "applies_to": "xbrl",
                       "pattern": r"^(?P<affiliate_status>[^,]+), (?P<investment_type>Equity, Warrants and Other Investments|[^,]+), (?P<industry>[^,]+), (?P<issuer>.+?)(?: - (?P<description>[^,]+?))?(?:, Interest Rate (?P<rate>.+?))?(?:, (?:Initial )?Acquisition Date (?P<issue_date>" + DATE + r"))?(?:, Maturity Date (?P<maturity>" + DATE + r"))?$",
                       "rate_parser": INV_RP},
                      {"id": "investcorp-html-issuer-description-v1", "source_field": "issuer_name", "applies_to": "html",
                       "pattern": r"^(?P<issuer>.+?) - (?P<description>[^-]+)$"}],
    normalization={"legal_suffixes": {"remove_preceding_comma": True}, "date_formats": ["%m/%d/%Y", "%Y-%m-%d"], "spread_input_unit": "percent", "spread_output_format": "decimal", "reference_index_aliases": {"S": "SOFR", "P": "Prime"}},
), hdr("Investcorp Credit Management BDC, Inc.", "1578348", "0001193125-26-352658", "2026-06-30"))

# ---------------------------------------------------------------- Jefferies Credit Partners BDC (1959604)
jef_ind = html_industry_headings("1959604")
JEF_RP = {"pattern": r"(?P<index>S|SOFR|P|Prime|E|EURIBOR|SN|SONIA)\s*\+\s*(?P<spread_pct>\d+(?:\.\d+)?)\s*%", "spread_unit": "percent", "index_aliases": {"S": "SOFR", "SOFR": "SOFR", "P": "Prime", "Prime": "Prime", "E": "EURIBOR", "SN": "SONIA"}}
TEMPLATES["1959604"] = (base(
    "1959604", "Jefferies Credit Partners BDC Inc.", "jefferies-credit-partners-2026-layout-v1", "2026-03-31",
    "Typed labels: 'NCNA Ptfl Cmp Invs {Section} {Industry} {Issuer} Investment Type {Description} Reference Rate and Spread S + 4.75% Maturity Date M/D/YYYY' plus commitment members 'Portfolio Company {Issuer} Investment Type {Description}' without monetary facts. HTML SOI in thousands: 'Portfolio Company | Investment Type | Reference Rate and Spread | Maturity Date | Principal / Shares | Cost | Fair Value' with an unfunded-commitment table (excluded).",
    ["0001193125-26-345216 (2026-06-30): 484 typed members; undimensioned fair value 1,906,400,000 and cost 1,914,843,000 within tolerance of the holdings sums",
     "0001193125-26-345216: 'S' supported by InvestmentVariableInterestRateTypeExtensibleEnumeration = SOFR on 308 members; 135 negative fair-value facts on unfunded facilities",
     "0001193125-26-221855 (2026-03-31) inspected as the prior period; industry vocabulary from HTML heading rows"],
    html={"header_aliases": {"issuer_name": ["^Portfolio Company"], "security_description": ["^Investment Type"], "interest_rate_text": ["^Reference Rate and Spread"], "cost": ["^Cost"], "fair_value": ["^Fair Value"], "maturity_date": ["^Maturity Date"]},
          "table_detection": {"heading_regex": ["Schedule of Investments"], "required_terms": ["Fair Value"], "excluded_terms": ["Fair Value Hierarchy", "Financial Highlights", "Unfunded Commitment", "Commitment Expiration"], "minimum_score": 6, "max_heading_distance": 20},
          "row_rules": {"carry_forward": [], "group_heading_target": "industry", "group_heading_rules": [{"regex": "affiliated|controlled", "target": "affiliate_status"}, {"regex": "Debt Investments|Equity Investments", "target": "investment_type"}], "total_if_regex": ["^Total Investments\\b(?!\\s+in\\s)", "^Total investments\\b(?!\\s+in\\s)"], "subtotal_if_regex": ["^Total\\b"], "require_any_numeric": ["fair_value", "cost", "principal_amount", "shares"]},
          "rate_parser": JEF_RP, "prefer_html_fields": ["issuer_name"]},
    composite_fields=[{"id": "jefferies-label-v1", "source_field": "issuer_name", "applies_to": "xbrl",
                       "pattern": r"^NCNA Ptfl Cmp Invs\s+(?P<investment_type>First Lien Debt Investments|Second Lien Debt Investments|Equity Investments|Debt Investments|Unsecured Debt Investments)\s+(?P<header>.+?)\s+Investment Type\s+(?P<description>.+?)(?:\s+Reference Rate and Spread\s+(?P<rate>.+?))?(?:\s+Maturity Date\s+(?P<maturity>" + DATE + r"))?$",
                       "header_parser": {"known_industries": jef_ind, "industry_position": "prefix", "remainder_target": "issuer_name"}, "rate_parser": JEF_RP},
                      {"id": "jefferies-commitment-label-v1", "source_field": "issuer_name", "applies_to": "xbrl", "pattern": r"^Portfolio Company\s+(?P<issuer>.+?)\s+Investment Type\s+(?P<description>.+)$"}],
    normalization={"legal_suffixes": {"remove_preceding_comma": True}, "date_formats": ["%m/%d/%Y", "%Y-%m-%d"], "spread_input_unit": "percent", "spread_output_format": "decimal", "reference_index_aliases": {"S": "SOFR", "P": "Prime"}},
    validation={"allow_negative_fair_value": True, "allow_negative_fair_value_evidence": "0001193125-26-345216: 135 negative InvestmentOwnedAtFairValue facts on unfunded revolver/delayed-draw members."},
), hdr("Jefferies Credit Partners BDC Inc.", "1959604", "0001193125-26-345216", "2026-06-30"))
