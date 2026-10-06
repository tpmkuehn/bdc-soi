"""Batch 1 templates: 26North, BIP Ventures, Barings, Chicago Atlantic, Commonwealth Credit Partners, Crescent Capital.
Every rule cites the inspected filing (see docs/coverage-report.md)."""

from write_templates import html_industry_headings  # type: ignore

DATE = r"\d{1,2}/\d{1,2}/\d{4}"


def base(cik, name, tid, eff_from, description, evidence, **kw):
    t = {
        "schema_version": 1, "cik": cik, "company_name": name,
        "templates": [{
            "id": tid, "priority": 100, "effective_from": eff_from, "effective_to": None, "forms": ["10-Q"], "status": "production",
            "description": description, "evidence": evidence,
            "xbrl": {"role_regex": ["Schedule of Investments"], "row_axes": {"explicit_qnames": ["us-gaap:InvestmentIdentifierAxis"], "exclude_regex": ["FairValue.*Hierarchy"]},
                     "context_filters": {"require_report_date": True, "allowed_period_types": ["instant"], "excluded_axes_regex": ["FairValueByFairValueHierarchyLevel"]},
                     "total_concepts": {"fair_value": ["us-gaap:InvestmentOwnedAtFairValue"], "cost": ["us-gaap:InvestmentOwnedAtCost"]}},
            "html": {"table_detection": {"heading_regex": ["Schedule of Investments"], "required_terms": ["Fair Value"], "excluded_terms": ["Fair Value Hierarchy", "Financial Highlights"], "minimum_score": 6, "max_heading_distance": 20},
                     "header_rows": {"min": 1, "max": 3}, "header_aliases": {}, "scale": {"source": "table_then_document", "thousands_regex": ["in thousands"], "default": 1},
                     "row_rules": {"carry_forward": [], "group_heading_target": "industry", "group_heading_rules": [{"regex": "affiliated|controlled", "target": "affiliate_status"}], "total_if_regex": ["^Total Investments\\b(?!\\s+in\\s)"], "subtotal_if_regex": ["^(?:Sub)?[Tt]otal\\b"], "require_any_numeric": ["fair_value", "cost", "amortized_cost", "principal_amount", "shares"]},
                     "prefer_html_fields": ["issuer_name"]},
            "composite_fields": [], "normalization": {"legal_suffixes": {"remove_preceding_comma": True}, "date_formats": ["%m/%d/%Y", "%Y-%m-%d"], "spread_input_unit": "auto", "spread_output_format": "decimal", "reference_index_aliases": {}},
            "validation": {}, "overrides": [],
        }],
    }
    tv = t["templates"][0]
    for k, v in kw.items():
        if isinstance(v, dict) and isinstance(tv.get(k), dict):
            tv[k].update(v)
        else:
            tv[k] = v
    return t


def hdr(name, cik, acc, report):
    return f"# Company template for {name} (CIK {cik}). Grounded in SEC accession {acc} (10-Q, report date {report});\n# a prior period was inspected as recorded in docs/coverage-report.md. Rules cite filing evidence in `evidence`.\n"


PCT_RP = {"pattern": r"(?:\d+\s*M(?:onth)?\s+)?(?P<index>SOFR|Prime|PRIME|S|P|EURIBOR|E|SONIA|CORRA|C|BBSY|B|BBSW|BKBM|SARON|STIBOR|NIBOR)\s*\+\s*(?:CSA\s*\+\s*)?(?P<spread_pct>\d+(?:\.\d+)?)\s*%?", "floor_pattern": r"(?P<floor_pct>\d+(?:\.\d+)?)\s*%\s*[Ff]loor", "pik_pattern": r"(?P<pik_pct>\d+(?:\.\d+)?)\s*%\s*PIK", "spread_unit": "percent",
          "index_aliases": {"SOFR": "SOFR", "S": "SOFR", "Prime": "Prime", "PRIME": "Prime", "P": "Prime", "EURIBOR": "EURIBOR", "E": "EURIBOR", "SONIA": "SONIA", "CORRA": "CORRA", "C": "CORRA", "BBSY": "BBSY", "B": "BBSY", "BBSW": "BBSW", "BKBM": "BKBM", "SARON": "SARON", "STIBOR": "STIBOR", "NIBOR": "NIBOR"}}

TEMPLATES = {}

# ---------------------------------------------------------------- 26North BDC (1950976)
TEMPLATES["1950976"] = (base(
    "1950976", "26North BDC, Inc.", "26north-bdc-2026-layout-v1", "2026-03-31",
    "Typed labels are pipe-delimited: 'Debt Investments | Issuer | Description | Industry | SOFR + 4.750 | 8.698% | acquisition | maturity' (6 or 7 parts; percent spreads without a % sign). HTML SOI in thousands with 'Portfolio Company | Investment Type | Industry | Reference Rate and Spread | Interest Rate | Acquisition Date | Maturity Date | Par Amount/ Shares | Amortized Cost | Fair Value | Percentage of Net Assets'; grand total row 'Total Portfolio Investments'; the undimensioned us-gaap:InvestmentOwnedAtFairValue ('Total Investments at Fair Value') includes short-term investments listed after that total.",
    ["0001193125-26-340235 (2026-06-30): 144 typed members; label parts separated by '|'; us-gaap:InvestmentBasisSpreadVariableRate = 0.0475 for label 'SOFR + 4.750' => percent unit",
     "0001193125-26-340235 HTML: 'Total Portfolio Investments $1,781,403 $1,768,802' equals the sum of XBRL holdings (cost 1,781,403,000 / fair value 1,768,802,000); 'Total Investments at Fair Value $1,818,784 $1,806,183' adds short-term investments => total_source_preference html_template_total",
     "0001193125-26-340235: HTML 'Amortized Cost' equals us-gaap:InvestmentOwnedAtCost on 128/128 matched rows => mapped to cost",
     "0001193125-26-340235: 42 negative us-gaap:InvestmentOwnedAtFairValue facts on unfunded revolver/delayed-draw members",
     "0001193125-26-214004 (2026-03-31) inspected as the prior period"],
    html={"header_aliases": {"issuer_name": ["^Portfolio Company"], "security_description": ["^Investment Type"], "industry": ["^Industry"], "interest_rate_text": ["^Reference Rate and Spread"], "interest_rate": ["^Interest Rate"], "cost": ["^Amortized Cost"], "fair_value": ["^Fair Value"], "maturity_date": ["^Maturity Date"]},
          "row_rules": {"carry_forward": [], "group_heading_target": "investment_type", "group_heading_rules": [{"regex": "affiliated|controlled", "target": "affiliate_status"}], "total_if_regex": ["^Total Portfolio Investments"], "subtotal_if_regex": ["^Total\\b"], "require_any_numeric": ["fair_value", "cost", "principal_amount", "shares"]},
          "rate_parser": PCT_RP, "prefer_html_fields": ["issuer_name"]},
    composite_fields=[{"id": "26north-pipe-label-v1", "source_field": "issuer_name", "applies_to": "xbrl",
                       "pattern": r"^(?P<section>[^|]+?)\s*\|\s*(?P<issuer>[^|]+?)\s*\|\s*(?P<description>[^|]+?)\s*\|\s*(?P<industry>[^|]+?)\s*(?:\|\s*(?P<rate>[^|]*?\+[^|]*?)\s*)?(?:\|\s*(?P<interest_rate>\d+(?:\.\d+)?\s*%)\s*)?(?:\|\s*" + DATE + r"\s*\|\s*(?P<maturity>" + DATE + r")\s*)?(?:\|\s*" + DATE + r"\s*)?$",
                       "capture_targets": {"section": "investment_type"}, "rate_parser": PCT_RP}],
    normalization={"legal_suffixes": {"remove_preceding_comma": True}, "date_formats": ["%m/%d/%Y", "%Y-%m-%d"], "spread_input_unit": "percent", "spread_output_format": "decimal", "reference_index_aliases": {"S": "SOFR"}},
    validation={"allow_negative_fair_value": True, "allow_negative_fair_value_evidence": "0001193125-26-340235: 42 negative fair-value facts, all unfunded revolver/delayed-draw commitments (HTML shows '(54)' style negatives).",
                "total_source_preference": ["html_template_total", "xbrl_no_dimensions"], "total_source_preference_evidence": "0001193125-26-340235: HTML 'Total Portfolio Investments' (1,781,403 / 1,768,802 thousands) equals the XBRL holdings sums; the undimensioned InvestmentOwnedAtFairValue (1,806,183) also includes short-term investments disclosed after that row."},
), hdr("26North BDC, Inc.", "1950976", "0001193125-26-340235", "2026-06-30"))

# ---------------------------------------------------------------- BIP Ventures Evergreen BDC (1950572)
bip_ind = html_industry_headings("1950572")
TEMPLATES["1950572"] = (base(
    "1950572", "BIP Ventures Evergreen BDC", "bip-ventures-2026-layout-v1", "2026-03-31",
    "Typed labels: 'Investments – non-controlled / affiliated {Section} {Industry} {Issuer} Type {Description} Acquisition Date M/D/YYYY [Interest Rate 10.0%] [Maturity Date M/D/YYYY]'. HTML SOI in whole dollars: 'Investments | Type | Acquisition Date | Interest Rate | Maturity Date | Par Amount/Units | Cost | Fair Value | % of Net Assets' with affiliation, section and industry heading rows; fixed-rate convertible notes and equity only.",
    ["0001193125-26-339708 (2026-06-30): 24 typed members; undimensioned InvestmentOwnedAtFairValue 157,635,546 equals the XBRL holdings sum; cost 122,573,899 equals",
     "0001193125-26-339708 HTML: whole-dollar amounts (e.g. $48,500,000) matching XBRL facts; industry vocabulary from HTML heading rows: " + ", ".join(bip_ind),
     "0001193125-26-214360 (2026-03-31) inspected as the prior period"],
    html={"header_aliases": {"issuer_name": ["^Investments"], "security_description": ["^Type$"], "interest_rate": ["^Interest Rate"], "cost": ["^Cost"], "fair_value": ["^Fair Value"], "maturity_date": ["^Maturity Date"]},
          "scale": {"source": "fixed", "fixed_multiplier": 1, "default": 1},
          "row_rules": {"carry_forward": [], "group_heading_target": "industry", "group_heading_rules": [{"regex": "affiliated", "target": "affiliate_status"}, {"regex": "^(Convertible Notes|Equity Investments|Unsecured Convertible Notes|Warrants|Preferred|Common)", "target": "investment_type"}], "total_if_regex": ["^Total investments\\b(?!\\s+in\\s)", "^Total Investments\\b(?!\\s+in\\s)"], "subtotal_if_regex": ["^Total\\b"], "require_any_numeric": ["fair_value", "cost", "principal_amount", "shares"]},
          "prefer_html_fields": ["issuer_name"]},
    composite_fields=[{"id": "bip-label-v1", "source_field": "issuer_name", "applies_to": "xbrl",
                       "pattern": r"^Investments [–-] (?P<affiliate_status>non-controlled / (?:non-)?affiliated)\s+(?P<header>.+?)\s+Type\s+(?P<description>.+?)(?:\s+Acquisition Date\s+" + DATE + r")?(?:\s+Interest Rate\s+(?P<interest_rate>\d+(?:\.\d+)?%))?(?:\s+Maturity Date\s+(?P<maturity>" + DATE + r"))?$",
                       "header_parser": {"known_industries": bip_ind, "industry_position": "infix", "remainder_target": "issuer_name"}}],
), hdr("BIP Ventures Evergreen BDC", "1950572", "0001193125-26-339708", "2026-06-30"))

# ---------------------------------------------------------------- Barings BDC (1379785)
bar_ind = html_industry_headings("1379785")
TEMPLATES["1379785"] = (base(
    "1379785", "Barings BDC, Inc.", "barings-bdc-2026-layout-v1", "2026-03-31",
    "Typed labels 'Issuer | Description[ | Funded]'. HTML SOI in thousands with 'Portfolio Company | Investment Type | Interest | Acq. Date | Maturity Date | Principal Amount | Cost | Fair Value | % of Net Assets | Notes'; interest text 'SOFR + 4.75%, 8.6% Cash'; maturity shown as MM/YY (not a full date; left null). Jocassee Partners LLC (consolidated subsidiary) holdings are tagged with a subsidiary axis and reported outside the entity-wide total.",
    ["0001379785-26-000030 (2026-06-30): 855 typed members, 149 without monetary facts (commitments); after excluding the Jocassee subsidiary-context row (33,180,000) the XBRL fair-value sum equals the undimensioned total 2,458,590,000",
     "0001379785-26-000030 HTML: index tokens SOFR, SONIA, BBSY, CORRA, BKBM, SARON, STIBOR, NIBOR (all unambiguous full names); 63 negative fair-value facts on unfunded facilities",
     "0001379785-26-000022 (2026-03-31) inspected as the prior period; industry vocabulary from HTML heading rows"],
    html={"header_aliases": {"issuer_name": ["^Portfolio Company"], "security_description": ["^Investment Type"], "interest_rate_text": ["^Interest$"], "cost": ["^Cost$"], "fair_value": ["^Fair Value"], "maturity_date": ["^Maturity Date"], "principal_amount": ["^Principal Amount"], "shares": ["^Units / Shares"], "footnote_markers": ["^Notes$"]},
          "row_rules": {"carry_forward": ["issuer_name"], "group_heading_target": "industry", "group_heading_rules": [{"regex": "affiliate|control", "target": "affiliate_status"}], "total_if_regex": ["^Total Investments\\b(?!\\s+in\\s)", "^Total investments\\b(?!\\s+in\\s)"], "subtotal_if_regex": ["^(?:Sub)?[Tt]otal\\b"], "require_any_numeric": ["fair_value", "cost", "principal_amount", "shares"]},
          "prefer_html_fields": ["issuer_name"]},
    xbrl={"role_regex": ["Schedule of Investments"], "row_axes": {"explicit_qnames": ["us-gaap:InvestmentIdentifierAxis"], "exclude_regex": ["FairValue.*Hierarchy"], "exclude_member_regex": [r"[|,]\s*Funded$"], "exclude_member_evidence": "0001379785-26-000030: members ending in '| Funded' or ', Funded' (e.g. 'Eclipse Business Capital Holdings LLC | Revolver | Funded' 12,900,000; 'Rocade Holdings LLC | Second Lien Secured Loan | Funded' 12,200,000) re-tag the funded portion of facilities that already appear as members and as single HTML rows; excluding them makes the XBRL sum equal 'Total Investments, June 30, 2026 $2,458,590'."},
          "context_filters": {"require_report_date": True, "allowed_period_types": ["instant"], "excluded_axes_regex": ["FairValueByFairValueHierarchyLevel"]},
          "total_concepts": {"fair_value": ["us-gaap:InvestmentOwnedAtFairValue"], "cost": ["us-gaap:InvestmentOwnedAtCost"]}},
    composite_fields=[{"id": "barings-pipe-label-v1", "source_field": "issuer_name", "applies_to": "xbrl", "kind": "delimited", "delimiter": "|", "positions": {"issuer": 0, "description": 1}, "min_parts": 2}],
    validation={"allow_negative_fair_value": True, "allow_negative_fair_value_evidence": "0001379785-26-000030: 63 negative InvestmentOwnedAtFairValue facts on unfunded revolver/delayed-draw members (HTML '(33)' style)."},
), hdr("Barings BDC, Inc.", "1379785", "0001379785-26-000030", "2026-06-30"))

# ---------------------------------------------------------------- Chicago Atlantic BDC (1843162)
TEMPLATES["1843162"] = (base(
    "1843162", "Chicago Atlantic BDC, Inc.", "chicago-atlantic-2026-layout-v1", "2026-03-31",
    "XBRL carries issuer, affiliation and type as extensible enumerations. HTML SOI in thousands: 'Portfolio Company | Facility Type | All in Rate | Benchmark | Spread | PIK | Floor | Initial Acquisition Date | Maturity | Par | Amortized Cost | Fair Value | % of Net Assets | Footnotes' with industry heading rows; benchmark letters S (SOFR), P (Prime), F (fixed).",
    ["0001193125-26-347342 (2026-06-30): 54 typed members; fair value 334,833,992 and cost 336,747,389 undimensioned facts equal the holdings sums",
     "0001193125-26-347342: HTML 'Amortized Cost(15)' equals us-gaap:InvestmentOwnedAtCost on 40/40 matched rows => cost; benchmark letters confirmed by us-gaap:InvestmentVariableInterestRateTypeExtensibleEnumeration values (Prime 19, SOFR 11, Fixed 10)",
     "0001193125-26-222738 (2026-03-31) inspected as the prior period"],
    html={"header_aliases": {"issuer_name": ["^Portfolio Company"], "security_description": ["^Facility Type", "^Class Series"], "interest_rate": ["^All in Rate"], "reference_index": ["^Benchmark"], "spread": ["^Spread"], "pik_rate": ["^PIK"], "rate_floor": ["^Floor"], "cost": ["^Amortized Cost", "^Cost$"], "fair_value": ["^Fair Value"], "maturity_date": ["^Maturity"], "principal_amount": ["^Par"], "shares": ["^Shares"], "footnote_markers": ["^Footnotes"]},
          "row_rules": {"carry_forward": [], "group_heading_target": "industry", "group_heading_rules": [{"regex": "affiliated|controlled", "target": "affiliate_status"}, {"regex": "^Investments at Fair Value|^US Corporate Debt|Senior Secured|Equity", "target": "ignore"}], "total_if_regex": ["^Total Investments\\b(?!\\s+in\\s)"], "subtotal_if_regex": ["^Total\\b"], "require_any_numeric": ["fair_value", "cost", "principal_amount", "shares"]},
          "prefer_html_fields": ["issuer_name"]},
    normalization={"legal_suffixes": {"remove_preceding_comma": True}, "date_formats": ["%m/%d/%Y", "%Y-%m-%d"], "spread_input_unit": "percent", "spread_output_format": "decimal", "reference_index_aliases": {"S": "SOFR", "P": "Prime"}},
), hdr("Chicago Atlantic BDC, Inc.", "1843162", "0001193125-26-347342", "2026-06-30"))

# ---------------------------------------------------------------- Commonwealth Credit Partners BDC I (1841514)
TEMPLATES["1841514"] = (base(
    "1841514", "Commonwealth Credit Partners BDC I, Inc.", "commonwealth-credit-2026-layout-v1", "2026-03-31",
    "Typed labels: 'Debt Investments, First Lien Senior Secured, {Issuer} - {Description}, {Industry}, Spread Above Index SOFR + 5.50% (1.00% floor) + 2.25% PIK Interest Rate 11.44% Maturity Date 5/10/2027' and equity 'Membership Interest Investments, Common Membership Interest, {Issuer} - {Description}, {Industry}'. HTML SOI in thousands; the first column combines issuer and facility ('190 Octane Financing, LLC - Term Loan'); cash equivalents are listed after 'Total Investments'.",
    ["0001193125-26-344908 (2026-06-30): 172 typed members; HTML 'Total Investments $669,057 $623,418' equals the undimensioned XBRL facts; HTML 'Amortized Cost' equals us-gaap:InvestmentOwnedAtCost on 118/118 matched rows => cost",
     "0001193125-26-344908: 10 negative fair-value facts on unfunded facilities; SOFR is the only index token in HTML rate text",
     "0001193125-26-219691 (2026-03-31) inspected as the prior period"],
    html={"header_aliases": {"issuer_name": ["^Portfolio Company"], "industry": ["^Industry"], "interest_rate_text": ["^Spread Above Index"], "interest_rate": ["^Interest Rate"], "cost": ["^Amortized Cost"], "fair_value": ["^Fair Value"], "maturity_date": ["^Maturity Date"]},
          "row_rules": {"carry_forward": [], "group_heading_target": "investment_type", "group_heading_rules": [{"regex": "affiliated|controlled", "target": "affiliate_status"}], "total_if_regex": ["^Total Investments\\b(?!\\s+in\\s)"], "subtotal_if_regex": ["^Total\\b"], "require_any_numeric": ["fair_value", "cost", "principal_amount", "shares"]},
          "rate_parser": PCT_RP, "prefer_html_fields": ["issuer_name"]},
    composite_fields=[
        {"id": "commonwealth-debt-label-v1", "source_field": "issuer_name", "applies_to": "xbrl",
         "pattern": r"^(?P<section>[^,]+), (?P<investment_type>[^,]+), (?P<issuer>.+?) - (?P<description>[^,]+), (?P<industry>[^,]+?),?\s+Spread Above Index\s+(?P<rate>.+?)\s+Interest Rate\s+(?P<interest_rate>\d+(?:\.\d+)?%)(?:\s+Maturity Date\s+(?P<maturity>" + DATE + r"))?$",
         "capture_targets": {"section": "sector"}, "rate_parser": PCT_RP},
        {"id": "commonwealth-equity-label-v1", "source_field": "issuer_name", "applies_to": "xbrl",
         "pattern": r"^(?P<section>[^,]+), (?P<investment_type>[^,]+), (?P<issuer>.+?) - (?P<description>[^,]+), (?P<industry>[^,]+)$", "capture_targets": {"section": "sector"}},
        {"id": "commonwealth-html-issuer-split-v1", "source_field": "issuer_name", "applies_to": "html", "pattern": r"^(?P<issuer>.+?) - (?P<description>.+)$"},
    ],
    normalization={"legal_suffixes": {"remove_preceding_comma": True}, "date_formats": ["%m/%d/%Y", "%Y-%m-%d"], "spread_input_unit": "percent", "spread_output_format": "decimal", "reference_index_aliases": {}},
    validation={"allow_negative_fair_value": True, "allow_negative_fair_value_evidence": "0001193125-26-344908: 10 negative InvestmentOwnedAtFairValue facts on unfunded revolving/delayed-draw facilities."},
), hdr("Commonwealth Credit Partners BDC I, Inc.", "1841514", "0001193125-26-344908", "2026-06-30"))

# ---------------------------------------------------------------- Crescent Capital BDC (1633336)
cres_ind = html_industry_headings("1633336")
CRES_RP = {"pattern": r"(?:Term\s+)?(?P<index>S|B|E|SN|P|C|SOFR|BBSY|EURIBOR|SONIA|Prime|CORRA)\s*\+\s*(?P<spread_bps>\d+(?:\.\d+)?)", "floor_pattern": r"(?P<floor_bps>\d+)\s*Floor", "pik_pattern": r"\((?P<pik_bps>\d+)\s*PIK\)", "spread_unit": "basis_points",
           "index_aliases": {"S": "SOFR", "SOFR": "SOFR", "B": "BBSY", "BBSY": "BBSY", "E": "EURIBOR", "EURIBOR": "EURIBOR", "SN": "SONIA", "SONIA": "SONIA", "P": "Prime", "Prime": "Prime", "C": "CORRA", "CORRA": "CORRA"}}
TEMPLATES["1633336"] = (base(
    "1633336", "Crescent Capital BDC, Inc.", "crescent-capital-2026-layout-v1", "2026-03-31",
    "Typed labels: 'Investments {Country} {Debt|Equity} Investments {Industry} {Issuer} Investment Type {Description} [Interest Term B + 500, 50 Floor] [Interest Rate 9.36%] [Maturity/ Dissolution Date MM/DD/YYYY]' with basis-point spreads and floors. HTML SOI in thousands with a title row above the header ('Country/Security/Industry/Company'); rate text 'S + 600 (425 PIK), 100 Floor'.",
    ["0001193125-26-342351 (2026-06-30): 859 typed members (208 without monetary facts); undimensioned fair value 1,570,668,000 and cost 1,625,061,000 equal the XBRL holdings sums",
     "0001193125-26-342351: index letters B (Australian holdings, enum BankBillSwapBid/BBSY), E (EURIBOR), S (SOFR, enum SecuredOvernightFinancingRate), P (Prime) supported by InvestmentVariableInterestRateTypeExtensibleEnumeration on the same members; floors stated in basis points ('100 Floor')",
     "0001193125-26-342351: 43 negative fair-value facts on unfunded facilities; industry vocabulary from HTML heading rows (GICS industry groups)",
     "0001193125-26-221936 (2026-03-31) inspected as the prior period"],
    html={"header_aliases": {"issuer_name": ["Country/Security/Industry/Company", "^Portfolio Company"], "security_description": ["^Security", "^Investment Type"], "interest_rate_text": ["^Interest Rate$|^Interest$|Spread"], "interest_rate": ["^Total Interest|^Current Interest"], "cost": ["^Cost$", "^Amortized Cost"], "fair_value": ["^Fair Value"], "maturity_date": ["^Maturity"], "principal_amount": ["^Principal|^Par"]},
          "row_rules": {"carry_forward": ["issuer_name"], "group_heading_target": "issuer_name", "group_heading_rules": [{"regex": "affiliated|controlled", "target": "affiliate_status"}, {"regex": "^(Debt|Equity) Investments", "target": "investment_type"}, {"regex": "^(United States|Canada|United Kingdom|Australia|Europe|Netherlands|Germany|France|Luxembourg|Ireland|Spain|New Zealand|Switzerland|Sweden|Norway|Denmark|Belgium|Italy)$", "target": "country"}], "total_if_regex": ["^Total Investments\\b(?!\\s+in\\s)"], "subtotal_if_regex": ["^Total\\b"], "require_any_numeric": ["fair_value", "cost", "principal_amount", "shares"]},
          "rate_parser": CRES_RP, "prefer_html_fields": ["issuer_name"]},
    composite_fields=[{"id": "crescent-label-v1", "source_field": "issuer_name", "applies_to": "xbrl",
                       "pattern": r"^Investments\s+(?P<country>.+?)\s+(?P<investment_type>Debt Investments|Equity Investments)\s+(?P<header>.+?)\s+Investment(?: Type)?\s+(?P<description>.+?)(?:\s+Interest\s+(?P<rate>.+?))?(?:\s+Interest Rate\s+(?P<interest_rate>\d+(?:\.\d+)?%))?(?:\s+Maturity/ ?Dissolution Date\s+(?P<maturity>" + DATE + r"))?$",
                       "header_parser": {"known_industries": cres_ind, "industry_position": "prefix", "remainder_target": "issuer_name"}, "rate_parser": CRES_RP}],
    normalization={"legal_suffixes": {"remove_preceding_comma": True}, "date_formats": ["%m/%d/%Y", "%Y-%m-%d"], "spread_input_unit": "basis_points", "spread_output_format": "decimal", "reference_index_aliases": {"S": "SOFR", "B": "BBSY", "E": "EURIBOR", "P": "Prime"}},
    validation={"allow_negative_fair_value": True, "allow_negative_fair_value_evidence": "0001193125-26-342351: 43 negative InvestmentOwnedAtFairValue facts on unfunded facilities."},
), hdr("Crescent Capital BDC, Inc.", "1633336", "0001193125-26-342351", "2026-06-30"))
