from datetime import date
from pathlib import Path

from bdc_soi.html_tables import Cell, classify_row, compress_columns, detect_dates, detect_header_rows, detect_scale, expand_grid, extract_html, flatten_headers, map_columns, _alias_patterns, _compile_list
from bdc_soi.normalization import parse_number
from bdc_soi.templates import HeaderRows, HtmlSpec, RowRules
from tests.conftest import SYN


def test_monetary_parsing():
    assert parse_number("$ 1,234,567").value == 1234567.0
    assert parse_number("(1,234)").value == -1234.0 and parse_number("(1,234)").negative
    assert parse_number("—").value is None and parse_number("—").kind == "null"
    assert parse_number("–").kind == "null" and parse_number("").kind == "null"
    p = parse_number("12,345 (4)")
    assert p.value == 12345.0 and p.footnotes == "(4)"
    assert parse_number("abc").kind == "text"
    assert parse_number("$(500)").value == -500.0


def test_percentage_and_bps_parsing():
    assert parse_number("4.50%").kind == "percent" and parse_number("4.50%").value == 4.5
    assert parse_number("450 bps").kind == "bps" and parse_number("450 bps").value == 450.0
    assert parse_number("(0.25)%").value == -0.25


def test_scale_detection():
    assert detect_scale("(dollar amounts in thousands)") == 1000
    assert detect_scale("($ in millions)") == 1_000_000
    assert detect_scale("in thousands, except share data") == 1000
    assert detect_scale("no scale here") is None
    assert detect_scale("amounts in thousands", millions=[r"amounts in thousands"]) == 1_000_000  # template priority


def test_multirow_header_flattening_and_column_compression():
    rows = [
        [Cell("Portfolio"), Cell(""), Cell("Amortized", 2), Cell("Fair", 2)],
        [Cell("Company"), Cell("Maturity"), Cell("Cost", 2), Cell("Value", 2)],
        [Cell("Acme"), Cell("1/1/2030"), Cell("$"), Cell("100"), Cell("$"), Cell("110")],
        [Cell("Beta"), Cell("—"), Cell(""), Cell("(5)"), Cell(""), Cell("7")],
    ]
    grid = expand_grid(rows, 2)
    grid, notes = compress_columns(grid, 2)
    headers = flatten_headers(grid, 2)
    assert headers == ["Portfolio Company", "Maturity", "Amortized Cost", "Fair Value"]
    assert grid[2] == ["Acme", "1/1/2030", "$100", "$110"] and grid[3][2] == "(5)"
    mapping, rules, _ = map_columns(headers, _alias_patterns(None))
    assert mapping == {0: "issuer", 1: "maturity_date", 2: "amortized_cost", 3: "fair_value"}


def test_split_parenthesis_column_merges_left():
    rows = [[Cell("Company"), Cell("Fair Value", 2)], [Cell("Acme"), Cell("(1,000"), Cell(")")], [Cell("Beta"), Cell("500"), Cell("")]]
    grid, _ = compress_columns(expand_grid(rows, 1), 1)
    assert grid[1] == ["Acme", "(1,000)"]


def test_industry_company_header_maps_to_issuer_not_industry():
    # Observed in Apollo Debt Solutions 10-Q: header "Industry/Company (14)" with industry and issuer as heading rows.
    headers = ["Industry/Company (14)", "Investment Type", "Interest Rate (13)", "Maturity Date", "Par/Shares/Units (3)", "Cost (36)", "Fair Value (1)(37)", ""]
    mapping, rules, notes = map_columns(headers, _alias_patterns(None))
    assert mapping[0] == "issuer" and mapping[1] == "description" and mapping[4] == "principal_or_shares" and mapping[5] == "cost" and mapping[6] == "fair_value"
    assert 7 not in mapping or mapping[7] == "footnote_markers"
    assert mapping.get(2) in {"interest_rate", "interest_rate_text"}


def test_positional_issuer_fallback_only_leading_column():
    headers = ["", "Investment Type", "Maturity", "Fair Value", ""]
    mapping, rules, notes = map_columns(headers, _alias_patterns(None))
    assert mapping[0] == "issuer"
    headers = ["Investment Type", "Maturity", "Fair Value", ""]
    mapping, rules, notes = map_columns(headers, _alias_patterns(None))
    assert 3 not in mapping  # a trailing blank column is never the issuer


def test_total_row_detection_precedence():
    mapping = {0: "issuer", 1: "fair_value"}
    rules = RowRules(skip_if_regex=["^Total"], total_if_regex=["Total Investments"], subtotal_if_regex=["^Total\\b"])
    compiled = {"total": _compile_list(rules.total_if_regex), "subtotal": _compile_list(rules.subtotal_if_regex), "skip": _compile_list(rules.skip_if_regex), "footnote": []}
    assert classify_row(["Total Investments", "1,000"], mapping, ["Company", "Fair Value"], rules, compiled)[0] == "total"
    assert classify_row(["Total Software", "500"], mapping, ["Company", "Fair Value"], rules, compiled)[0] == "subtotal"
    assert classify_row(["Totally Different Co", "500"], mapping, ["Company", "Fair Value"], rules, compiled)[0] == "skipped"
    assert classify_row(["Acme", "500"], mapping, ["Company", "Fair Value"], rules, compiled)[0] == "holding"
    assert classify_row(["Software", ""], mapping, ["Company", "Fair Value"], rules, compiled)[0] == "group_heading"
    assert classify_row(["Company", "Fair Value"], mapping, ["Company", "Fair Value"], rules, compiled)[0] == "repeated_header"
    assert classify_row(["", ""], mapping, ["Company", "Fair Value"], rules, compiled)[0] == "blank"


def test_date_detection():
    assert detect_dates("Consolidated Schedule of Investments as of June 30, 2025 (Unaudited) and December 31, 2024") == ["2025-06-30", "2024-12-31"]


def _syn_html(spec=None, report_date=date(2025, 6, 30), known=None):
    return extract_html(SYN / "package" / "syn-20250630.htm", report_date, spec or HtmlSpec(row_rules=RowRules(carry_forward=["issuer"], group_heading_target="industry")), known_group_values=known)


def test_synthetic_table_selection_period_and_scale():
    ex = _syn_html()
    accepted = [t for t in ex.tables if t.accepted]
    assert len(accepted) == 1 and accepted[0].period_status == "current"
    assert accepted[0].scale_multiplier == 1000 and accepted[0].scale_source in {"nearest_heading", "table_local_text", "document_soi_heading_window"}
    rejected = {t.table_id: t for t in ex.tables if not t.accepted}
    comparative = [t for t in rejected.values() if t.period_status == "comparative"]
    assert comparative and any("comparative_period_table" in r for t in comparative for r in t.reasons)
    assert any("excluded_terms" in r for t in rejected.values() for r in t.reasons)  # fair value hierarchy table


def test_issuer_carry_forward_and_group_heading_boundaries():
    ex = _syn_html(known={"industry": {"Software", "Healthcare"}})
    rows = ex.holding_rows
    assert len(rows) == 5
    issuers = [r.fields.get("issuer") for r in rows]
    assert issuers == ["Redwood Runway Bidco, LLC", "Redwood Runway Bidco, LLC", "Alpine Health Services, Inc.", "Alpine Health Services, Inc.", "Alpine Health Services, Inc."]
    assert rows[1].carried["issuer"] == rows[0].row_id and "issuer" not in rows[0].carried
    assert [r.fields.get("industry") for r in rows] == ["Software", "Software", "Healthcare", "Healthcare", "Healthcare"]
    assert rows[0].fields["fair_value"] == 10050000.0 and rows[0].fields["principal_amount"] == 10000000.0 and rows[0].fields["amortized_cost"] == 9900000.0
    assert rows[4].fields.get("maturity_date") in (None, "") and rows[4].fields["amortized_cost"] == 500000.0
    assert rows[4].fields.get("shares") == 1000.0 and "principal_amount" not in rows[4].fields and rows[0].fields["principal_amount"] == 10000000.0
    assert rows[0].fields["footnote_markers"] or rows[0].footnotes


def test_issuer_short_name_heading_under_known_industry_targets_issuer():
    # Apollo layout: industry heading, then issuer short-name heading; only the industry is a known value.
    ex = _syn_html(spec=HtmlSpec(row_rules=RowRules(carry_forward=["issuer"], group_heading_target="issuer")), known={"industry": {"Software", "Healthcare"}})
    rows = ex.holding_rows
    assert rows[0].fields["industry"] == "Software" and rows[0].fields["issuer"] == "Redwood Runway Bidco, LLC"
    assert rows[1].fields["issuer"] == "Redwood Runway Bidco, LLC"


def test_interest_rate_text_column_is_parsed_not_dropped():
    ex = _syn_html()
    r = ex.holding_rows[0]
    assert r.fields.get("interest_rate_text") == "SOFR + 4.50%, 0.50% Floor"


def test_html_total_candidates_and_subtotals():
    ex = _syn_html()
    totals = [t for t in ex.totals if t.source in {"html_generic_total", "html_template_total"}]
    assert {(t.field, t.value) for t in totals} == {("amortized_cost", 22280000.0), ("fair_value", 22450000.0)}
    assert any(t.source == "html_subtotal" and t.value == 12050000.0 for t in ex.totals)


def test_numeric_only_row_is_subtotal_not_holding():
    # Apollo run 1: issuer subtotal rows (numbers only) became holdings once a heading supplied the issuer.
    mapping = {0: "issuer", 1: "description", 2: "cost", 3: "fair_value"}
    rules = RowRules()
    compiled = {"total": [], "subtotal": _compile_list(["^Total\\b"]), "skip": [], "footnote": []}
    assert classify_row(["", "", "192,508", "193,793"], mapping, ["Company", "Type", "Cost", "Fair Value"], rules, compiled)[0] == "subtotal"
    assert classify_row(["", "First Lien Term Loan", "1,000", "1,010"], mapping, ["Company", "Type", "Cost", "Fair Value"], rules, compiled)[0] == "holding"


def test_period_uses_nearest_dated_block(tmp_path):
    # Apollo: the comparative schedule's first page followed a geography table mentioning the current date.
    html = """<html><body>
    <p>Consolidated Schedule of Investments June 30, 2026</p><p>(in thousands)</p>
    <table><tr><td>Company</td><td>Fair Value</td></tr><tr><td>Acme</td><td>1,000</td></tr><tr><td>Total Investments</td><td>1,000</td></tr></table>
    <p>Geographic Region Percentage of Total Investments (at Fair Value) as of June 30, 2026 United States 76.0%</p>
    <p>Consolidated Schedule of Investments December 31, 2025</p>
    <table><tr><td>Company</td><td>Fair Value</td></tr><tr><td>Acme</td><td>900</td></tr><tr><td>Total Investments</td><td>900</td></tr></table>
    </body></html>"""
    p = tmp_path / "doc.htm"
    p.write_text(html)
    ex = extract_html(p, date(2026, 6, 30), HtmlSpec(table_detection=__import__("bdc_soi.templates", fromlist=["TableDetection"]).TableDetection(minimum_score=3)))
    statuses = {t.table_index: t.period_status for t in ex.tables}
    assert statuses[0] == "current" and statuses[1] == "comparative"


def test_rows_after_grand_total_are_marked():
    ex = _syn_html(spec=HtmlSpec(row_rules=RowRules(carry_forward=["issuer"], total_if_regex=["^Total Software"])))
    # With "Total Software" declared as the grand total, the healthcare rows that follow are after-total rows.
    after = [r for r in ex.holding_rows if "after_total_row" in r.notes]
    assert len(after) == 3 and all("Alpine" in r.fields["issuer"] for r in after)


def test_heading_values_are_cleaned_and_ignore_rule_works(tmp_path):
    from bdc_soi.html_tables import clean_heading_value
    from bdc_soi.templates import GroupHeadingRule

    assert clean_heading_value("BANK LOANS: NON-CONTROL/NON-AFFILIATE INVESTMENTS (h) (i) (Continued):") == "BANK LOANS: NON-CONTROL/NON-AFFILIATE INVESTMENTS"
    assert clean_heading_value("Services: Business") == "Services: Business"
    html = """<html><body><p>Schedule of Investments June 30, 2026</p>
    <table><tr><td>Portfolio Company</td><td>Investment Type</td><td>Fair Value</td></tr>
    <tr><td>Acme BDC, Inc. (Continued)</td></tr><tr><td>Services: Business</td></tr>
    <tr><td>Vortex</td><td>1st Lien Term Loan</td><td>1,000</td></tr></table></body></html>"""
    p = tmp_path / "d.htm"
    p.write_text(html)
    spec = HtmlSpec(table_detection=__import__("bdc_soi.templates", fromlist=["TableDetection"]).TableDetection(minimum_score=3), row_rules=RowRules(group_heading_rules=[GroupHeadingRule(regex=r"^Acme BDC", target="ignore")]))
    ex = extract_html(p, date(2026, 6, 30), spec)
    assert ex.holding_rows[0].fields["industry"] == "Services: Business" and "sector" not in ex.holding_rows[0].fields


def test_dash_only_cells_are_not_descriptive_evidence():
    mapping = {0: "issuer", 1: "description", 2: "cost", 3: "fair_value"}
    compiled = {"total": [], "subtotal": _compile_list(["^Total\\b"]), "skip": [], "footnote": []}
    assert classify_row(["", "", "(2,500)", "—"], mapping, ["Company", "Type", "Cost", "Fair Value"], RowRules(), compiled)[0] == "subtotal"


def test_title_row_is_caption_not_header(tmp_path):
    # Crescent Capital: a single cell spanning the table repeats the schedule title above the real header.
    html = """<html><body><p>Schedule of Investments</p>
    <table><tr><td colspan="4">CRESCENT CAPITAL BDC, Inc. Consolidated Schedule of Investments June 30, 2026 (in thousands)</td></tr>
    <tr><td>Portfolio Company</td><td>Investment Type</td><td>Cost</td><td>Fair Value</td></tr>
    <tr><td>Acme</td><td>Term Loan</td><td>1,000</td><td>1,010</td></tr></table></body></html>"""
    p = tmp_path / "d.htm"
    p.write_text(html)
    ex = extract_html(p, date(2026, 6, 30), None)
    t = ex.tables[0]
    assert t.flattened_headers == ["Portfolio Company", "Investment Type", "Cost", "Fair Value"] and t.accepted and t.period_status == "current" and t.scale_multiplier == 1000
    assert ex.holding_rows[0].fields["issuer"] == "Acme"


def test_rollforward_tables_are_excluded(tmp_path):
    html = """<html><body><p>Schedule of Investments June 30, 2026</p>
    <table><tr><td>Portfolio Company</td><td>Type of Asset</td><td>Beginning Fair Value</td><td>Gross Additions</td><td>Fair Value at June 30, 2026</td></tr>
    <tr><td>Acme</td><td>Term Loan</td><td>900</td><td>100</td><td>1,000</td></tr></table></body></html>"""
    p = tmp_path / "d.htm"
    p.write_text(html)
    ex = extract_html(p, date(2026, 6, 30), None)
    assert not ex.tables[0].accepted and any("excluded_terms" in r for r in ex.tables[0].reasons)


def test_money_market_total_and_net_asset_rows():
    mapping = {0: "issuer", 1: "fair_value"}
    compiled = {"total": _compile_list(__import__("bdc_soi.html_tables", fromlist=["GENERIC_TOTAL_REGEX"]).GENERIC_TOTAL_REGEX), "subtotal": _compile_list(["^Total\\b"]), "skip": _compile_list(__import__("bdc_soi.html_tables", fromlist=["NON_HOLDING_ROW_REGEX"]).NON_HOLDING_ROW_REGEX), "footnote": []}
    assert classify_row(["Total Investments in Money Market Funds", "25,184"], mapping, ["Company", "Fair Value"], RowRules(), compiled)[0] == "subtotal"
    assert classify_row(["Total Investments", "1,000"], mapping, ["Company", "Fair Value"], RowRules(), compiled)[0] == "total"
    assert classify_row(["Liabilities in Excess of Other Assets", "(141,677)"], mapping, ["Company", "Fair Value"], RowRules(), compiled)[0] == "skipped"
    from bdc_soi.normalization import collapse_ws

    assert collapse_ws("​ Investments ​") == "Investments"


def test_repeated_header_columns_merge_and_heading_percent_suffix():
    from bdc_soi.html_tables import clean_heading_value, merge_repeated_header_columns

    grid = [["Company", "Spread Above Index", "Spread Above Index", "Fair Value"], ["Acme", "SF +", "5.50%", "100"]]
    g2, h2, merged = merge_repeated_header_columns(grid, grid[0], 1)
    assert merged and h2 == ["Company", "Spread Above Index", "Fair Value"] and g2[1] == ["Acme", "SF + 5.50%", "100"]
    assert clean_heading_value("Multifamily - 158.9%") == "Multifamily" and clean_heading_value("Senior Mortgage – 219.7%") == "Senior Mortgage"


def test_issuer_named_total_with_facility_is_a_holding():
    # Commonwealth Credit Partners: 'Total Fleet Buyer, LLC - Term Loan ... 7/12/2030 6,756 6,672 6,756' is a holding.
    mapping = {0: "issuer", 1: "industry", 2: "interest_rate_text", 3: "maturity_date", 4: "cost", 5: "fair_value"}
    compiled = {"total": [], "subtotal": _compile_list(["^Total\\b"]), "skip": [], "footnote": []}
    hdrs = ["Portfolio Company", "Industry", "Spread", "Maturity Date", "Cost", "Fair Value"]
    assert classify_row(["Total Fleet Buyer, LLC - Term Loan", "Capital Goods", "SOFR + 4.50%", "7/12/2030", "6,672", "6,756"], mapping, hdrs, RowRules(), compiled)[0] == "holding"
    assert classify_row(["Total Capital Goods", "", "", "", "6,672", "6,756"], mapping, hdrs, RowRules(), compiled)[0] == "subtotal"


def test_rating_tables_excluded_and_template_known_industries(tmp_path):
    from bdc_soi.html_tables import GENERIC_EXCLUDED_TERMS

    assert any("Rating" in p for p in GENERIC_EXCLUDED_TERMS)
    html = """<html><body><p>Schedule of Investments June 30, 2026</p>
    <table><tr><td>Portfolio Company</td><td>Investment Type</td><td>Fair Value</td></tr>
    <tr><td>IT Services</td></tr><tr><td>Acme Corp</td><td>One stop</td><td>1,000</td></tr></table></body></html>"""
    p = tmp_path / "d.htm"
    p.write_text(html)
    spec = HtmlSpec(table_detection=__import__("bdc_soi.templates", fromlist=["TableDetection"]).TableDetection(minimum_score=3), row_rules=RowRules(known_industries=["IT Services"]))
    # The XBRL vocabulary says 'Information Technology Services'; the template vocabulary recognises the HTML heading.
    ex = extract_html(p, date(2026, 6, 30), spec, known_group_values={"industry": {"Information Technology Services", "IT Services"}})
    assert ex.holding_rows[0].fields["industry"] == "IT Services"


def test_spilled_subtotal_label_is_not_holding_evidence():
    # Apollo: 'Total Oil, Gas & Consumable Fuels $188,271 $187,903' spans into the interest-rate column.
    mapping = {0: "issuer", 1: "description", 2: "interest_rate_text", 3: "maturity_date", 5: "cost", 6: "fair_value"}
    compiled = {"total": [], "subtotal": _compile_list(["^Total\\b"]), "skip": [], "footnote": []}
    hdrs = ["Industry/Company", "Investment Type", "Interest Rate", "Maturity Date", "Par", "Cost", "Fair Value"]
    assert classify_row(["Total Oil, Gas & Consumable Fuels", "", "Total Oil, Gas & Consumable Fuels", "", "", "188,271", "187,903"], mapping, hdrs, RowRules(), compiled)[0] == "subtotal"
    assert classify_row(["Total Fleet Buyer, LLC - Term Loan", "", "SOFR + 4.50%", "7/12/2030", "", "6,672", "6,756"], mapping, hdrs, RowRules(), compiled)[0] == "holding"


def test_continuation_page_without_header_inherits_previous_mapping(tmp_path):
    # Golub: several SOI pages carry no repeated header row; their rows were dropped before this rule.
    html = """<html><body><p>Consolidated Schedule of Investments June 30, 2026 (in thousands)</p>
    <table><tr><td>Portfolio Company</td><td>Investment Type</td><td>Cost</td><td>Fair Value</td></tr>
    <tr><td>Acme</td><td>One stop</td><td>1,000</td><td>1,010</td></tr></table>
    <p>Consolidated Schedule of Investments (continued) June 30, 2026</p>
    <table><tr><td>Bayshore Intermediate #2, L.P.</td><td>One stop</td><td>126,992</td><td>125,131</td></tr>
    <tr><td>Beta</td><td>One stop</td><td>10</td><td>11</td></tr></table>
    <p>Notes to financial statements. Schedule of Investments footnotes.</p><table><tr><td>Other table</td><td>x</td><td>y</td></tr><tr><td>a</td><td>b</td><td>c</td></tr></table>
    <table><tr><td>Net operating expenses</td><td>$ 13,057,924</td><td>$ 9,690,012</td><td>34.8%</td></tr><tr><td>Management fee</td><td>3,084,381</td><td>2,606,206</td><td>18.3%</td></tr></table></body></html>"""
    p = tmp_path / "d.htm"
    p.write_text(html)
    ex = extract_html(p, date(2026, 6, 30), None)
    assert ex.tables[1].accepted and any(r.startswith("inherited_header_from_table_0") for r in ex.tables[1].reasons)
    issuers = [r.fields["issuer"] for r in ex.holding_rows]
    assert issuers == ["Acme", "Bayshore Intermediate #2, L.P.", "Beta"] and ex.holding_rows[1].fields["fair_value"] == 125131000.0
    assert not ex.tables[3].accepted  # a later unrelated table of the same width is not a continuation page


def test_leading_blank_rows_do_not_consume_header_budget():
    # Stellus: a blank first row plus three header rows ('Principal', 'Investment', 'Investments | Footnotes | ...').
    rows = [[Cell(""), Cell("")], [Cell(""), Cell("Principal", 2)], [Cell("Investment"), Cell("Amount/", 2)], [Cell("Date"), Cell("Shares")], [Cell("2/24/2022"), Cell("2,753,323")]]
    assert detect_header_rows(rows, HtmlSpec(header_rows=HeaderRows(min=1, max=3)), _alias_patterns(None)) == 4


def test_currency_symbols_are_captured_and_inherited_down_the_column(tmp_path):
    from bdc_soi.html_tables import disclosed_currency

    assert disclosed_currency("$ 1,000") == ("USD", "$") and disclosed_currency("£ 62,182") == ("GBP", "£") and disclosed_currency("C$ 7,791") == ("CAD", "C$") and disclosed_currency("1,000") == (None, None)
    html = """<html><body><p>Schedule of Investments June 30, 2026 (in thousands)</p>
    <table><tr><td>Portfolio Company</td><td>Investment Type</td><td>Par</td><td>Fair Value</td></tr>
    <tr><td>Acme</td><td>Term Loan</td><td>$ 100</td><td>$ 101</td></tr>
    <tr><td>Pathfinder</td><td>Term Loan</td><td>£ 62,182</td><td>81,244</td></tr></table></body></html>"""
    p = tmp_path / "d.htm"
    p.write_text(html)
    ex = extract_html(p, date(2026, 6, 30), None)
    r = ex.holding_rows[1]
    assert r.currency_symbols["principal_amount"] == {"code": "GBP", "symbol": "£", "source_row_id": r.row_id}
    assert r.currency_symbols["fair_value"] == {"code": "USD", "symbol": "$", "source_row_id": ex.holding_rows[0].row_id}


def test_header_less_page_can_borrow_the_next_page_layout(tmp_path):
    # Golub: pages 14/32/37 share their column count with the following header page, not the preceding one.
    html = """<html><body><p>Consolidated Schedule of Investments June 30, 2026 (in thousands)</p>
    <table><tr><td>Portfolio Company</td><td>Investment Type</td><td>Cost</td><td>Fair Value</td></tr>
    <tr><td>Acme</td><td>One stop</td><td>1,000</td><td>1,010</td></tr></table>
    <p>Consolidated Schedule of Investments (continued) June 30, 2026</p>
    <table><tr><td>Bayshore</td><td></td><td>One stop</td><td>126,992</td><td>125,131</td></tr>
    <tr><td>Beta</td><td></td><td>One stop</td><td>10</td><td>11</td></tr><tr><td>Gamma</td><td></td><td>One stop</td><td>5</td><td>6</td></tr></table>
    <p>Consolidated Schedule of Investments (continued) June 30, 2026</p>
    <table><tr><td>Portfolio Company</td><td></td><td>Investment Type</td><td>Cost</td><td>Fair Value</td></tr>
    <tr><td>Delta</td><td></td><td>One stop</td><td>7</td><td>8</td></tr></table></body></html>"""
    p = tmp_path / "d.htm"
    p.write_text(html)
    ex = extract_html(p, date(2026, 6, 30), None)
    issuers = [r.fields["issuer"] for r in ex.holding_rows]
    assert issuers == ["Acme", "Bayshore", "Beta", "Gamma", "Delta"]
    assert any(r.startswith("inherited_header_from_table_2") for r in ex.tables[1].reasons) and ex.holding_rows[1].fields["fair_value"] == 125131000.0


def test_undated_headed_table_after_grand_total_is_rejected(tmp_path):
    # Onex: a comparative-period page without a detectable date followed the 'Total Investments' row and duplicated rows.
    html = """<html><body><p>Schedule of Investments</p>
    <table><tr><td colspan="4">Consolidated Schedule of Investments June 30, 2026</td></tr><tr><td>Portfolio Company</td><td>Investment Type</td><td>Cost</td><td>Fair Value</td></tr>
    <tr><td>Acme</td><td>Term Loan</td><td>1,000</td><td>1,010</td></tr><tr><td>Total Investments</td><td></td><td>1,000</td><td>1,010</td></tr></table>
    <table><tr><td>Notes</td><td>x</td></tr><tr><td>y</td><td>z</td></tr></table>
    <table><tr><td>Portfolio Company</td><td>Investment Type</td><td>Cost</td><td>Fair Value</td></tr>
    <tr><td>Acme</td><td>Term Loan</td><td>900</td><td>910</td></tr></table></body></html>"""
    p = tmp_path / "d.htm"
    p.write_text(html)
    ex = extract_html(p, date(2026, 6, 30), None)
    assert ex.tables[0].accepted and not ex.tables[2].accepted and "rejected:undated_headed_table_after_grand_total" in ex.tables[2].reasons  # not adjacent to the total
    assert len(ex.holding_rows) == 1


def test_page_wrapper_block_containing_prior_statement_does_not_leak_excluded_terms(tmp_path):
    # Stellus / Crescent / TriplePoint: each page is a <div> wrapping its title and its table. Walking back from the
    # first SOI page reached the previous page's wrapper, whose full text ("Change in Unrealized") rejected the SOI page.
    html = """<html><body>
    <div><p>Consolidated Statements of Cash Flows June 30, 2026</p>
    <table><tr><td>Net change in unrealized appreciation</td><td>1,000</td></tr><tr><td>Change in Unrealized</td><td>2,000</td></tr></table>
    <p>Page break text</p></div>
    <div><p>Consolidated Schedule of Investments June 30, 2026 (in thousands)</p>
    <table><tr><td>Portfolio Company</td><td>Investment Type</td><td>Cost</td><td>Fair Value</td></tr>
    <tr><td>Acme</td><td>First Lien</td><td>1,000</td><td>1,010</td></tr><tr><td>Beta</td><td>First Lien</td><td>10</td><td>11</td></tr></table></div>
    </body></html>"""
    p = tmp_path / "d.htm"
    p.write_text(html)
    ex = extract_html(p, date(2026, 6, 30), None)
    soi = ex.tables[1]
    assert soi.accepted and not any(r.startswith("excluded_terms") for r in soi.reasons)
    assert "Page break text" in soi.heading_text and "Change in Unrealized" not in soi.heading_text


def test_iso_currency_code_prefixed_numbers_parse():
    # Crescent: 'CHF 19,009' principal cells (Solvias AG) were text, so the issuer subtotal row looked descriptive.
    assert parse_number("CHF 19,009").value == 19009.0 and parse_number("CHF 0").value == 0.0
    assert parse_number("CHF —").kind == "null" and parse_number("19,009 EUR").value == 19009.0
    assert parse_number("CHF").kind == "text" and parse_number("Chief").kind == "text"


def test_currency_coded_numbers_only_row_is_subtotal():
    mapping = {0: "issuer", 1: "description", 2: "principal_amount", 3: "cost", 4: "fair_value"}
    rules = RowRules()
    compiled = {"total": [], "subtotal": _compile_list(["^Total\\b"]), "skip": [], "footnote": []}
    heads = ["Company", "Type", "Principal", "Cost", "Fair Value"]
    assert classify_row(["", "", "CHF 19,009", "$20,657", "$23,763"], mapping, heads, rules, compiled)[0] == "subtotal"
    assert classify_row(["Solvias AG", "Term Loan", "CHF 19,009", "20,708", "23,763"], mapping, heads, rules, compiled)[0] == "holding"


def test_industry_heading_resets_issuer_group_context(tmp_path):
    # TriplePoint: 'Entertainment' (not in the XBRL industry vocabulary) became an issuer context and was later
    # written into blank-issuer tranche rows under 'Healthcare Technology Systems'.
    html = """<html><body><p>Consolidated Schedule of Investments June 30, 2026 (in thousands)</p>
    <table><tr><td>Portfolio Company</td><td>Type of Investment</td><td>Cost</td><td>Fair Value</td></tr>
    <tr><td>Entertainment</td><td></td><td></td><td></td></tr>
    <tr><td>Mind Candy Limited</td><td>Growth Capital Loan</td><td>21,221</td><td>10,758</td></tr>
    <tr><td>Healthcare Technology Systems</td><td></td><td></td><td></td></tr>
    <tr><td>Lively, Inc.</td><td>Growth Capital Loan</td><td>3,204</td><td>3,204</td></tr>
    <tr><td></td><td>Growth Capital Loan</td><td>3,204</td><td>3,204</td></tr></table></body></html>"""
    p = tmp_path / "d.htm"
    p.write_text(html)
    ex = extract_html(p, date(2026, 6, 30), None, known_group_values={"industry": {"Healthcare Technology Systems"}})
    rows = ex.holding_rows
    assert rows[0].fields.get("issuer") == "Mind Candy Limited"
    assert rows[2].fields.get("issuer") in (None, "", "Lively, Inc.")
    assert rows[2].fields["industry"] == "Healthcare Technology Systems"


def test_numeric_positional_issuer_column_rejects_summary_table(tmp_path):
    # Crescent Note 4 'Investments at fair value consisted of the following': an investment-type summary with two
    # dated cost/fair value column groups was accepted once the previous page's text stopped leaking (D36); its
    # positional 'issuer' column holds cost figures.
    html = """<html><body><p>Schedule of Investments at fair value consisted of the following as of June 30, 2026 (in thousands)</p>
    <table><tr><td>Investment Type</td><td>As of June 30, 2026 Cost</td><td>Fair Value</td><td>Unrealized</td><td>As of December 31, 2025 Cost</td><td>Fair Value</td><td>Unrealized</td></tr>
    <tr><td>Senior Secured First Lien</td><td>$388,464</td><td>$373,862</td><td>$(14,602)</td><td>$370,529</td><td>$350,795</td><td>$(19,734)</td></tr>
    <tr><td>Unitranche First Lien</td><td>1,069,697</td><td>1,039,165</td><td>(30,532)</td><td>1,068,444</td><td>1,047,747</td><td>(20,697)</td></tr>
    <tr><td>Total</td><td>1,458,161</td><td>1,413,027</td><td>(45,134)</td><td>1,438,973</td><td>1,398,542</td><td>(40,431)</td></tr></table></body></html>"""
    p = tmp_path / "d.htm"
    p.write_text(html)
    ex = extract_html(p, date(2026, 6, 30), None)
    t = ex.tables[0]
    assert not t.accepted and any(r.startswith("positional_issuer_column_numeric") for r in t.reasons)
    assert "issuer" not in t.column_mapping.values()


def test_heading_row_with_footnote_and_location_cells_is_group_heading(tmp_path):
    # Stellus: 'Bart & Associates, LLC | (4) | ... | McLean, VA' is the portfolio-company heading; the footnote cell
    # made it a three-text row and it fell to 'unknown'. The heading value is the name cell, not the whole row.
    html = """<html><body><p>Consolidated Schedule of Investments June 30, 2026</p>
    <table><tr><td>Portfolio Company</td><td>Notes</td><td>Security</td><td>Headquarters/ Industry</td><td>Cost</td><td>Fair Value</td></tr>
    <tr><td>Bart &amp; Associates, LLC</td><td>(4)</td><td></td><td>McLean, VA</td><td></td><td></td></tr>
    <tr><td></td><td>(7)</td><td>First Lien</td><td>High Tech Industries</td><td>2,005,093</td><td>2,032,093</td></tr></table></body></html>"""
    p = tmp_path / "d.htm"
    p.write_text(html)
    ex = extract_html(p, date(2026, 6, 30), None, known_group_values={"industry": {"High Tech Industries"}})
    assert ex.tables[0].rows[0].classification == "group_heading"
    row = ex.holding_rows[0]
    assert row.fields.get("issuer") == "Bart & Associates, LLC" and row.carried.get("issuer") == "group_heading"


def test_combined_par_shares_equity_row_with_na_maturity_is_shares(tmp_path):
    # Onex: 'Wash & Wax Holdings LLC | Class A Common Share | 4/30/2025 | N/A | 1,440 | 3,309,552 | —' put 1,440 into
    # principal_amount because the literal 'N/A' maturity counted as debt evidence; XBRL carries 1,440 shares.
    html = """<html><body><p>Consolidated Schedule of Investments June 30, 2026</p>
    <table><tr><td>Portfolio Company</td><td>Security</td><td>Maturity</td><td>Par / Shares</td><td>Cost</td><td>Fair Value</td></tr>
    <tr><td>Wash &amp; Wax Holdings LLC</td><td>Class A Common Share</td><td>N/A</td><td>1,440</td><td>3,309,552</td><td>—</td></tr>
    <tr><td>Wash &amp; Wax Systems LLC</td><td>First Lien Term Loan</td><td>4/30/2030</td><td>3,512,053</td><td>3,416,876</td><td>3,512,053</td></tr></table></body></html>"""
    p = tmp_path / "d.htm"
    p.write_text(html)
    ex = extract_html(p, date(2026, 6, 30), None)
    rows = ex.holding_rows
    assert rows[0].fields.get("shares") == 1440.0 and "principal_amount" not in rows[0].fields
    assert rows[1].fields.get("principal_amount") == 3512053.0
