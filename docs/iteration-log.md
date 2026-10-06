# Iteration log

Evidence for each refinement cycle (SPEC 20/21). "Before/after" numbers are counts measured on the named
run directories under `output/` (local, not committed). None of these are accuracy metrics against
reviewed golden data; no reviewed golden dataset exists yet (see docs/progress.md).

## Iteration 001 — first live end-to-end run (generic engine only)

### Filing
CIK 1837532 (Apollo Debt Solutions BDC), accession 0001193125-26-341358, 10-Q, report date 2026-06-30.
Verified via SEC submissions API on 2026-10-06; extracted instance `ck0001837532-20260630_htm.xml`.

### Result
`inspect` completed: 869 holdings (835 XBRL groups on `us-gaap:InvestmentIdentifierAxis` + 34 appended HTML rows),
58 HTML tables accepted, reconciliation `ambiguous_total`. Run: `output/inspect_apollo_q2_2026`.

### Failures observed, categories and remedies (each with a failing test added first)
| # | Failure | Category | Remedy (narrowest) | Test |
| --- | --- | --- | --- | --- |
| 1 | Header "Industry/Company (14)" mapped to industry; positional fallback picked the trailing footnote column as issuer | header reconstruction | generic issuer aliases (`Industry/Company`, `\bIssuer\b`), positional fallback limited to leading columns, footnote-marker column heuristic | `test_industry_company_header_maps_to_issuer_not_industry`, `test_positional_issuer_fallback_only_leading_column` |
| 2 | "Interest Rate" column text (`S+425, 0.50% Floor`) dropped as unparsed numeric | header reconstruction / composite parsing | non-numeric cells in an interest-rate column become `interest_rate_text` | `test_interest_rate_text_column_is_parsed_not_dropped` |
| 3 | Reference index exported as `//fasb.org/us-gaap/2025# Secured Overnight Financing Rate Sofr` | normalization | `normalize_reference_index_enum` alias table | `test_reference_index_extensible_enumeration_normalized` |
| 4 | Issuer short-name heading rows ("Accel International") overwrote the industry | row classification / carry-forward | known classification vocabulary (XBRL members) decides heading level; unknown headings become issuer-level | `test_issuer_short_name_heading_under_known_industry_targets_issuer` |
| 5 | Non-USD principal units made `currency` null and blocked reconciliation | normalization / total selection | instrument currency from principal unit; `reporting_currency` from the fair-value unit | `test_currency_from_principal_unit_and_reporting_currency` |
| 6 | `us-gaap:InvestmentIssuerNameAxis` members not used as issuer | concept mapping | generic dimension-field rule for issuer-name axes | `test_issuer_name_axis_member_is_direct_issuer_source` |
| 7 | HTML total rows from the generic template ranked above the undimensioned XBRL fact | total selection | SPEC 16.1 ranks implemented explicitly | `test_total_candidate_ranks_follow_spec_16_1` |

### After (generic engine, same filing, `output/inspect_apollo_q2_2026_v2`)
866 holdings, 56 tables accepted; XBRL-only detail sums equal the undimensioned totals exactly
(fair value 25,367,235,000; cost 25,641,832,000 vs 25,642,943,000 within tolerance); status `review`
because appended unmatched HTML rows inflated the detail sum. Regression: 87 offline tests passed.

## Iteration 002 — Apollo company template, first version

### Failure
Issuer remained the entire typed member label (`Aerospace & Defense Accel International Accel International
Holdings, LLC Investment Type ...`); 781/869 rows carried an issuer conflict against HTML.

### Root cause
No company template: the typed `InvestmentIdentifierAxis` label is a composite
`{Industry} {Issuer short name} {Issuer legal name} Investment Type {Description} Interest Rate {Rate} Maturity Date {M/D/YYYY}`.

### Remedy
Template `templates/1837532.yml` (`apollo-debt-solutions-2026-layout-v1`): explicit holding axis, composite rule
`apollo-member-label-layout-v1` with the filing's 63 industry-axis labels as `known_industries`, `remainder_pattern`
for the duplicated short name, S/E/C/B/P index aliases supported by the filing's SOFR extensible-enumeration facts,
`carry_forward: [issuer]`, `group_heading_target: issuer`, grand-total regex `^Total Investments before Cash Equivalents`.

### Result (`output/apollo_q2_2026_run1`)
1,077 holdings (253 html_only), reconciliation `ambiguous_total`. New failures:

| # | Failure | Category | Remedy | Test |
| --- | --- | --- | --- | --- |
| 8 | Template total concept matched every dimensioned subtotal fact (rank 0) | total selection | template total concepts apply to undimensioned facts only | `test_template_total_concept_matches_only_undimensioned_facts` |
| 9 | Numeric-only issuer-subtotal rows became holdings once headings supplied an issuer | row classification | rows without descriptive text are subtotals | `test_numeric_only_row_is_subtotal_not_holding` |
| 10 | Typed label carries a brand name ("Authentic Brands") while HTML discloses the legal name | normalization precedence | template `html.prefer_html_fields: [issuer]` (never supersedes a direct XBRL fact; conflict recorded) | `test_prefer_html_fields_supersedes_composite_text_but_not_direct_facts` |
| 11 | 34 labels without `Investment Type`/`Interest Rate` keywords unmatched | composite parsing | second rule `apollo-member-label-layout-v2`; `composite_no_match` flag only when no rule matches | `test_composite_no_match_flag_only_when_no_rule_matches` |
| 12 | Instrument currencies (EUR/GBP/CAD) flagged as unexpected | validation | check the reporting currency | `test_row_rules_and_confidence` |

### After (`output/apollo_q2_2026_run2`)
837 holdings (13 html_only), 792 matched; XBRL/hybrid detail sums equal reported totals; status `review`.

## Iteration 003 — comparative period leakage and remaining formats

| # | Failure | Category | Remedy | Test |
| --- | --- | --- | --- | --- |
| 13 | First page of the comparative (2025-12-31) schedule accepted as current because a preceding geography table mentioned the current date | HTML table detection | period decided by the nearest dated block | `test_period_uses_nearest_dated_block` |
| 14 | `5.38% Cash plus 5.38% PIK`, `12.50% PIK` unknown rate formats | composite parsing | generic cash/PIK and PIK-only branches | `test_additional_rate_formats_observed_in_apollo_labels` |
| 15 | `N/A` maturity cells produced parser flags | normalization | N/A treated as null without diagnostic | `test_na_dates_are_null_without_diagnostic` |
| 16 | "Paper & Forest Products" not split from issuer ("Paper And Forest Products" in XBRL) | composite parsing | punctuation-insensitive industry prefix | `test_industry_prefix_tolerates_ampersand_vs_and` |
| 17 | Term loan matched to the revolver row with identical amounts | XBRL/HTML matching | description-mismatch penalty | `test_description_mismatch_penalty_resolves_identical_monetary_rows` |
| 18 | v1 label without the `Interest Rate` keyword absorbed the rate into the description | composite parsing (template) | tightened v1 pattern; N/T/K aliases (NIBOR/TONAR/KORIBOR members present) | `tests/regression/test_apollo_template_rules.py` |

### After (`output/apollo_q2_2026_run3`)
826 holdings (2 html_only: the two money-market cash-equivalent rows listed after the grand total), 790 matched,
comparative table rejected, XBRL detail = reported total exactly.

## Iteration 004 — after-total rows, review-queue noise, negative fair values

| # | Failure | Category | Remedy | Test |
| --- | --- | --- | --- | --- |
| 19 | Cash-equivalent rows after "Total Investments before Cash Equivalents" inflated the detail sum | total selection | rows after the grand total excluded from the sum with a note (`html_row_after_total`) | `test_after_total_rows_excluded_from_reconciliation_with_note` |
| 20 | 528 informational composite diagnostics entered the review queue | diagnostics | only problem diagnostics become flags | (covered by run 4 flag counts) |
| 21 | 135 disclosed negative fair values (unfunded revolvers/delayed draws, all `xbrl_fact`) flagged | validation | template `validation.allow_negative_fair_value` with mandatory evidence text | `test_template_allows_negative_fair_value_only_with_evidence` |

### After (`output/apollo_q2_2026_run4`, and other periods)
| Run | Holdings | Matched | html_only | FV detail vs reported | Cost detail vs reported | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Q2 2026 run4 | 826 | 790 | 2 | 25,367,235,000 = 25,367,235,000 | 25,641,832,000 vs 25,642,943,000 | review (mixed reporting currencies) |
| Q1 2026 run1 | 798 | 759 | 1 | 25,172,081,000 vs 25,149,083,000 (within 0.5%) | 25,426,426,000 = | review (mixed reporting currencies) |
| Q2 2025 run1 (filing agent 0000950170) | 711 | 669 | 7 | 19,896,167,000 vs 19,896,145,000 | 19,676,654,000 vs 19,670,193,000 | review |

Status stays `review` because a handful of Apollo fair-value facts are tagged in GBP/CAD/EUR units while the
total is USD; the engine does not combine currencies without a disclosed rule (SPEC conversion note).
Q1 2026 also surfaced 31 `InvestmentBasisSpreadVariableRate` facts tagged as 4.50 instead of 0.045; they are
flagged `spread_out_of_bounds` and `composite_conflict` rather than rescaled.

## Iteration 005 — second company (Audax Credit BDC, CIK 1633858)

### Filing
Accession 0001193125-26-348682, 10-Q, report date 2026-06-30, whole-dollar amounts.

### Generic baseline (`output/inspect_audax_latest`)
712 holdings; fair value 383,150,883 and cost 404,197,839 reconciled exactly against undimensioned XBRL facts
(status pass) before any template; 362 issuer conflicts; 194 commitment members without monetary facts.

| # | Failure | Category | Remedy | Test |
| --- | --- | --- | --- | --- |
| 22 | Issuer/industry/type disclosed as extensible-enumeration facts (`ns#Member`) exported raw | concept mapping / normalization | enumeration values resolved to member labels in the inventory; generic industry enumeration mapping | `test_extensible_enumeration_values_resolve_to_member_labels` |
| 23 | 194 commitment-schedule members (rate/maturity facts only) became holdings | context grouping | groups without any monetary field are excluded with a filing note | `test_groups_without_monetary_values_are_not_holdings` |
| 24 | HTML `Spread` (`5.00%`), `Interest Rate` (`8.73%`), `Index` (`S+`) cells stored as text | normalization | `coerce_html_rate_fields` with template aliases (no global S = SOFR) | `test_html_rate_cells_are_coerced_with_template_aliases` |
| 25 | Percent-formatted spread inside the label (`Index S + Spread 4.75% Interest Rate 8.48%`) | composite parsing (template) | `RateParser.interest_rate_pattern`; Audax rules v1 (section), commitment, equity-section | `tests/regression/test_audax_template_rules.py` |
| 26 | Page-header rows ("Audax Credit BDC, Inc. (Continued)") captured as sector; "(Continued):" noise in affiliation | row classification | heading value cleanup; `group_heading_rules` target `ignore` | `test_heading_values_are_cleaned_and_ignore_rule_works` |
| 27 | XBRL industry axis names differ from HTML sector headings, so headings were demoted and industry went stale (283 conflicts) | carry-forward logic | template composite `known_industries` are recognised as heading vocabulary | `test_template_industry_vocabulary_recognised_in_html_headings` |
| 28 | `(2,500) —` numeric-only rows classified as holdings (dash counted as text) | row classification | dash cells are not descriptive evidence | `test_dash_only_cells_are_not_descriptive_evidence` |

### After (`output/audax_q2_2026_run2`)
466 holdings (451 hybrid, 14 XBRL-only, 1 html_only), fair value pass (exact), cost pass (404,197,277 vs
404,197,839), no null issuer/description/industry, mean confidence 0.733, 20 description disagreements and
16 composite-vs-fact conflicts left in the review queue.

## Determinism evidence
`output/apollo_q2_2026_run5` vs `run6` (identical inputs, offline): all normalized artifacts byte-identical
(holdings.csv/parquet/json, validation, matching, axis, table, review queue, long facts, filings, template usage,
html rows, total candidates); `run_manifest.json` identical outside the declared operational fields. `output.xlsx`
differed only by the workbook `dcterms:modified` stamp, now pinned (fix applied after run6; verified by
`test_cached_rerun_is_deterministic` and the live test's checksum comparison).

# Session 2 (2026-10-06): universe extension to 26 companies

Baseline preserved before any change in `output/baseline_s2/` (tests: 115 passed, 1 skipped; Apollo and Audax
offline runs with state checksums). All 26 CIKs verified against the SEC submissions API; registrant names in
`config/bdc_universe.yml` and `docs/coverage-report.md`. Latest 10-Q and one prior period retrieved live and
cached for all 24 new companies (`output/s2_inspect_<cik>_{latest,prior}`), then extracted offline with the
generic engine (`output/s2_generic_<cik>_latest`) to collect template evidence before any template was written.

## Iteration 006 — Apollo unit issues investigated against the instances
Evidence: 8 fair-value facts per Apollo filing tagged GBP/CAD/EUR have no USD counterpart, equal the USD HTML
cells and sum exactly to the USD total; 31 Q1-2026 spread facts tagged 4.75 carry `decimals=2` against 4
elsewhere. Remedy: HTML-confirmed reporting currency (D24, `test_html_confirms_reporting_currency_without_converting_values`);
spread facts stay flagged. Category: normalization / filer inconsistency.

## Iteration 007 — generic defects found across the 24 generic runs (failing test first for each)
| # | Failure (companies) | Category | Remedy | Test |
| --- | --- | --- | --- | --- |
| 29 | Typed label = concatenated HTML cells; issuer kept as full label (most filers) | normalization | containment precedence D25 | `test_html_cell_contained_in_label_supersedes_label_derived_issuer` |
| 30 | Title row replicated into every header cell (Crescent, TriplePoint) | header reconstruction | caption rows | `test_title_row_is_caption_not_header` |
| 31 | Roll-forward / non-accrual / unfunded-commitment / rating tables accepted (BIP, Commonwealth, Jefferies, Goldman Sachs) | HTML table detection | generic excluded terms | `test_rollforward_tables_are_excluded`, `test_rating_tables_excluded_and_template_known_industries` |
| 32 | Section-node members summing their children (Investcorp) | context grouping | parent rule with >=2 children | `test_parent_section_members_are_excluded_when_children_sum`, `test_single_prefixed_sibling_is_not_a_parent` |
| 33 | 'Total Investments' / 'Net Assets' members on the axis (PIMCO, Muzinich) | context grouping | exact-phrase non-holding members -> total candidates | `test_total_and_net_asset_members_are_not_holdings_but_total_candidates`, `test_issuer_named_total_is_a_holding_member` |
| 34 | Subsidiary-context facts (Barings Jocassee subtotals) | total selection | `xbrl_subsidiary_context` exclusion | `test_subsidiary_context_holdings_are_flagged`, `test_subsidiary_context_rows_excluded_from_reconciliation` |
| 35 | 'Total Investments in Money Market Funds' taken as grand total (Kayne, West Bay) | total selection | lookahead in generic total regex | `test_money_market_total_and_net_asset_rows` |
| 36 | 'Liabilities in Excess of Other Assets' rows as holdings (Onex, Muzinich) | row classification | generic skip rows | same test |
| 37 | Zero-width characters in headers (Stellus) | header reconstruction | invisible-char stripping | same test |
| 38 | Split 'Spread Above Index' columns under one header (Golub) | header reconstruction | merge repeated-header columns | `test_repeated_header_columns_merge_and_heading_percent_suffix` |
| 39 | Heading values 'Multifamily - 158.9%' (Franklin BSP) | row classification | suffix cleanup | same test |
| 40 | Issuer 'Total Fleet Buyer, LLC' classified as subtotal (Commonwealth) | row classification | holding-like fields override | `test_issuer_named_total_with_facility_is_a_holding` |
| 41 | Dash-only numeric rows as holdings (Onex) | row classification | dash cells not descriptive | `test_dash_only_cells_are_not_descriptive_evidence` |
| 42 | Mixed-currency review triggered by rows without fair value (Crescent) | validation | ignore rows without FV | `test_dominant_currency_ignores_rows_without_fair_value` |
| 43 | XBRL industry names differ from HTML headings -> industry stale (Audax earlier, Golub) | carry-forward logic | template `known_industries` | `test_rating_tables_excluded_and_template_known_industries` |
| 44 | Matched rows reconcile but XBRL-only rows absent from HTML exceed total (Barings prior) | total selection | `review` with XBRL-only note | `test_matched_rows_reconcile_but_xbrl_only_rows_exceed_total_is_review` |

Template-layer capabilities added with tests: delimited composite rules, `total_source_preference`,
`exclude_member_regex`, `known_industries`, `infix` industry position, `interest_rate_pattern`, rate-capture
coercion (`test_delimited_composite_rule`, `test_total_source_preference_reranks_candidates`,
`test_template_member_exclusion_with_evidence`, `test_infix_industry_and_rate_capture_coercion`).

## Iteration 008 — company templates (24 new), two periods each
Per-company before/after reconciliation outcomes and remaining blockers are tabulated in
`docs/coverage-report.md` (generated from the final universe run). Template-specific failures fixed during
the batches: Barings `| Funded` and `, Funded` re-tagged members (exclusion with evidence), 26North and Muzinich
total source preference, Investcorp section aggregates, Muzinich hierarchy leaves only, Kayne Anderson fixed
scale 1000 and Muzinich/Onex/BIP/Palmer Square/Stellus fixed scale 1, Stellus partial-word header aliases,
Golub index-letter legend (SF/E/P/SN/A/CA) taken from the filing footnote.

## Iteration 009 — regression caught by the baseline comparison (Apollo)
### Failure
Universe run `output/universe_s2_run1` added 55 `html_only` rows to Apollo Q2 2026 versus `output/baseline_s2/apollo_q2_2026`
(820 -> 875): industry subtotal rows such as 'Total Oil, Gas & Consumable Fuels $188,271 $187,903' became holdings.
### Root cause (row classification)
Iteration 007 #40 let a 'Total …' row through when a facility/rate/maturity field was present; Apollo's subtotal label
spans into the interest-rate column, so the label itself counted as rate evidence.
### Remedy
`_holding_like_fields`: evidence must be a parsable date, a rate-looking cell (digit, % or +) or a description that is not
the spilled label. Failing test first: `test_spilled_subtotal_label_is_not_holding_evidence` (also guards the Commonwealth
'Total Fleet Buyer, LLC' holding). Universe reruns: `output/universe_s2_run3` (final) and `run4` (determinism);
prior periods rerun as `output/s2_final_<cik>_<accession>`.
### Regression
208 offline tests passed; Audax unchanged versus baseline (466 rows, no field changes); Apollo differences versus baseline are
limited to the HTML-confirmed reporting currency (8 rows) and the removed subtotal rows.

# Session 3 (2026-10-06): reconciliation audit, blockers, review package

## Iteration 010 — full-output reconciliation (D31) and excluded candidates (D32)
Failure class: total selection / reporting. Status previously could read "review" when matched rows reconciled;
now the complete exported output decides, with a bridge. Failing tests first: `test_full_output_reconciliation_bridge_uses_all_exported_holdings`,
`test_matched_rows_reconciling_never_implies_full_output_reconciles`, `test_affiliate_schedule_members_become_excluded_candidates`.
New artifacts: `reconciliation_bridge.csv`, `excluded_candidates.csv`.

## Iteration 011 — Golub Capital BDC (HTML table detection)
Evidence: the "missing" 309 identifier-axis members are report-date holdings with principal, cost, fair value and
spread facts, no extra dimensions; their positions are present in the HTML (e.g. 'Bayshore Intermediate #2, L.P.+(25)
One stop SF +5.50% ... 127,037 126,992 3.4 125,131') on pages whose tables carry no repeated header row (tables 14,
16, 22, 25, 32, 37, 40, 46), which scored 1.0 and were rejected. Remedy D34 (continuation pages inherit the previous
page's compression layout and mapping; adjacent or "(continued)" only). Tests: `test_continuation_page_without_header_inherits_previous_mapping`.
Golub's one-part members ('Chestnut Optical Midco, Inc.') carry investments-in-affiliates roll-forward concepts and
are excluded candidates (D32), not holdings.

## Iteration 012 — Chicago Atlantic prior-period JV member
Evidence: member 'CO Acquisition Vehicle LLC' (2026-03-31 fair value 17,370,481) carries
`InvestmentsInAndAdvancesToAffiliatesAtFairValueGrossAdditions`, `DebtAndEquitySecuritiesUnrealizedGainLoss`,
`GrossInvestmentIncomeOperating` and no principal/rate/maturity facts, while the schedule row for the same
investment is the detailed member '... Cannabis CO Acquisition Vehicle, LLC Facility Type Term Loan ...'. It belongs
to the investments-in-affiliates schedule (outside the SOI total); excluded candidate with evidence (D32).

## Iteration 013 — Stellus zero-width-space layout (header reconstruction)
Evidence: a blank first row, three header rows whose words are split across rows ('Principal'/'Amount/'/'Shares (3)',
'Amortized'/'Cost', 'Fair'/'Value (1)') and zero-width-space spacer cells between every column. Root cause: leading
blank rows consumed the header-row budget so the third header row was treated as data. Remedy: header budget counts
header rows only (`test_leading_blank_rows_do_not_consume_header_budget`); invisible characters are stripped only
in the parsing representation (original cell text is kept in `html_rows.csv`). HTML re-enabled in the template; the
score threshold returned to 6 and '% of Total Investments' summary tables are excluded generically.

## Iteration 014 — Apollo currency auditability (D33)
Failing test first: `test_html_currency_symbol_evidence_overrides_xbrl_unit_but_preserves_it`. HTML cells now carry
disclosed currency symbols (captured and carried down the column, `test_currency_symbols_are_captured_and_inherited_down_the_column`);
the reporting-currency conflict preserves the XBRL unit/fact/value and the HTML symbol/row/value; equal values alone
no longer override the unit.

## Iteration 015 — review package
`review-package` (stratified workbook) and `import-review` (validated import) commands; sample-scoped evaluation;
`test_workbook_export_import_and_sample_scoped_evaluation`.

## Iteration 016 — equal-valued tranche groups (XBRL/HTML matching)
Failure: PIMCO, West Bay and Stellus exported the same facilities twice (XBRL-only and HTML-only) when an issuer
had N identical-valued tranches: the one-to-one matcher left them ambiguous (equal best scores). Remedy: the
SPEC 14.2 table-sequence feature as a deterministic tie-break, applied only when the ambiguous XBRL group and the
free HTML group have the same size, identical values and pairwise-agreeing descriptions; matched rows carry
`matched_by_sequence_tiebreak` and `sequence_tiebreak_equal_valued_group`. Indistinguishable rows (no description
evidence) stay ambiguous. Test: `test_equal_valued_group_is_matched_by_sequence_when_counts_agree`.

## Iteration 017 — undated headed tables after the grand total (HTML table detection)
Failure: Onex's comparative-period page carried no detectable date, followed the 'Total Investments' row and was
accepted as current, duplicating 15 holdings as HTML-only rows (28.0M). Remedy: a table with its own header row that
follows the grand-total row without a current-period date is rejected
(`rejected:undated_headed_table_after_grand_total`). Test: `test_undated_headed_table_after_grand_total_is_rejected`.

## Iteration 018 — first schedule page rejected by the previous page's text (D36)
Failure: Stellus (tables 10/11, 111 rows), Crescent (table 9) and TriplePoint (table 12, 43 rows) lost their first
SOI pages because the previous page's wrapper `<div>` (cash-flow / changes-in-net-assets statement) was read as
heading text and matched an excluded term; the lost rows surfaced as XBRL-only (Stellus 90 rows / 89.5M,
TriplePoint 27 rows / 148.9M). Remedy: blocks wrapping a table contribute only text after their last nested table.
Test: `test_page_wrapper_block_containing_prior_statement_does_not_leak_excluded_terms`.

## Iteration 019 — currency-coded cells and unlabelled issuer subtotals (D37)
Failure: Crescent's Solvias AG rows carry `CHF` principal cells; `CHF 19,009` parsed as text, so the label-less
issuer subtotal row became a holding (HTML-only 23.8M, Greencross/Ancora 31.7M likewise). Remedy: ISO codes strip
to a number (`test_iso_currency_code_prefixed_numbers_parse`) and currency-only cells do not make a row descriptive
(`test_currency_coded_numbers_only_row_is_subtotal`).

## Iteration 020 — stale issuer heading context (D38)
Failure: TriplePoint's 'Entertainment' heading (absent from the XBRL industry vocabulary) became an issuer context
and was written into blank-issuer tranche rows two groups later (`Entertainment | Growth Capital Loan` x2).
Remedy: non-issuer headings clear the issuer context (`test_industry_heading_resets_issuer_group_context`); the
TriplePoint template carries `issuer_name` forward with the table_15 rows 31-33 evidence.

## Iteration 021 — summary table accepted after D36 (D39)
Failure: once the previous page's text stopped leaking, Crescent's Note 4 investment-type summary (two dated
cost/fair value groups) scored 6.25 and exported seven "holdings" whose issuer was a cost figure (HTML-only 1.56B).
Remedy: a positional issuer column with numeric cells is rejected (`test_numeric_positional_issuer_column_rejects_summary_table`).

## Iteration 022 — Stellus layout: portfolio-company heading rows (D40, template)
Failure: 'Bart & Associates, LLC | (4) | McLean, VA' heading rows fell to 'unknown' (three text cells), the
'Investments' column was mapped as the issuer (so debt rows had issuer 'Term Loan') and the typed labels
'{Company}, {Security}' did not parse for '... Class G Shares', 'Term Loan (PBDC SPV)', 'Term A Loan',
'Revolver One'; '&amp;' survived in typed members ('Bart amp; Associates'). Remedies: footnote cells are not row
content and issuer headings use the name cell (`test_heading_row_with_footnote_and_location_cells_is_group_heading`);
entity decoding of typed-member text (`test_typed_member_labels_are_entity_decoded`); the template maps
'Investments' to the security description, 'Security' to the investment type and headings to the issuer, with a
comma-aware label pattern (seven new label samples). Result: both Stellus periods reconcile (latest fair value exact).

## Iteration 023 — TriplePoint grand total and Onex zero-fair-value equity rows
TriplePoint: 'Total Investments in Portfolio Companies' is the schedule total (equal to the XBRL undimensioned
totals); the template total rule now names it (`test_triplepoint_grand_total_row_is_the_total_and_cash_equivalents_follow_it`)
so the money-market row after it is an after-total row; both periods reconcile. Onex: equity rows with 'N/A'
maturity put their share count into principal (`test_combined_par_shares_equity_row_with_na_maturity_is_shares`);
with shares matched the two zero-fair-value rows pair up.

## Iteration 024 — Investcorp double counting (D41)
Failure reproduced: `test_combined_par_shares_uses_investment_type_heading_when_description_is_in_issuer_cell`,
label samples for the four-part equity labels, and `test_exact_issuer_key_separates_near_identical_share_classes`.
Root causes: the section name 'Equity, Warrants and Other Investments' broke the comma-delimited label rule (issuer
kept the whole label); the HTML issuer cell held '{Issuer} - {Description}' unsplit; the share count went to
principal because the row quotes a PIK rate; A-1/B-1 share classes with equal share counts tied on fuzzy issuer
similarity. Remedies: label rule accepts the comma-bearing section and splits ' - ', an HTML issuer-cell rule, a
combined-column cross-field comparison in the matcher (`test_combined_par_shares_column_is_compared_against_either_xbrl_quantity`;
an equity-section heading rule was tried first and reverted after it broke Commonwealth, BIP and Golub rows whose unit
counts are tagged as principal), `issuer_exact` feature. Result (`output/s3_t14_1578348_*`, then final runs):
49/49 and 58/58 rows matched, fair value and cost reconcile exactly in both periods; no row removed.

## Iteration 025 — coverage matrix, decision pack, triage batch (D42)
`scripts/coverage_matrix.py` (52-row matrix, worse-period company status), `docs/decision-pack.md`, `review-package
--profile triage --blocker-budget 40 --blocker-inventory` (`test_triage_profile_is_small_and_keeps_blocker_inventory_separate`).
Final runs `output/universe_s3_run7` / `run8` (determinism 18/18 identical) and `output/s3d_final_*`.

## Iteration 026 — independent review corrections (D43-D45)
- Scope: 20 passing filings had complete exported sums outside tolerance; the passes rested on after-total exclusions.
  Rows now carry an explicit scope with rule and evidence (`test_reconciliation_scope_keeps_cash_equivalents_outside_and_subsidiary_sections_inside`);
  Audax's subsidiary equity section (after the total, inside the XBRL total) stays in scope; the bridge reports the
  scoped and the complete status side by side.
- Period coverage: Audax's 2026-03-31 10-Q (0001193125-26-219725) retrieved live and added; its template started at
  2026-06-30 so the prior period had fallen back to the generic template (HTML: no rows); effective_from moved to
  2026-03-31 with evidence (`test_every_universe_company_has_a_template_covering_its_prior_report_date`). Apollo's
  2025-06-30 run is reported as an additional historical test outside the 52-filing count.
- BIP e6e2ce8c08e96f0136b09e8829ef102c: filer XBRL inconsistency (CareSave-labelled member, acquisition date
  12/12/2024, carries the June figures printed for Integrative Life Network Class A; the Integrative member has only
  December facts). Matching on equal money with contradictory identity is rejected
  (`test_contradictory_identity_is_not_merged_on_equal_values`); both candidates exported and flagged.
- TriplePoint: prior-period labels 'Issuer | Description | Non-Affiliated' put the affiliation into investment_type
  for 101 rows; the label rule now names the section vocabulary and maps affiliation to affiliate_status
  (`test_triplepoint_affiliation_segment_is_not_an_investment_type`, three label samples).
- Sequence tie-break audit (127 rows, 48 groups): 45 groups have distinct descriptions on both sides (row identity),
  the rest only group equivalence; group-level representation implemented
  (`test_group_equivalent_pairing_is_recorded_at_group_level_not_as_row_identity`).
- Conflict classes and the `unresolved` review outcome (`test_conflict_classes_separate_formatting_from_identity_semantic_and_numeric`,
  `test_unresolved_decision_is_logged_but_never_becomes_a_golden_label`); workbook exposes reporting currency, original
  XBRL unit and principal currency separately, scope and identity columns, decision-case rows and an
  excluded-candidates sheet.

## Iteration 027 — targeted corrections (D33 revised, D46, D47)
- BIP: both contradictory candidates were counted in schedule scope (differences 142,480 / 522,718 passed tolerance).
  Identity acceptance is now separate from numerical reconciliation and blocked while a contradiction is unresolved;
  the XBRL candidate is scoped as a duplicate from sibling-member evidence, not from the totals
  (`test_contradictory_duplicate_is_outside_the_sums_and_blocks_acceptance_regardless_of_tolerance`,
  `test_contradictory_candidate_is_scoped_as_duplicate_only_with_sibling_member_evidence`); the XBRL counterpart now
  appears in the blocker inventory.
- Scope counts: 446 rows across 31 filings had no fair value and were absent from the published counts; counts for
  all exported rows are published next to counts with the field; explicit default rule for schedule rows; a
  subsidiary dimension alone no longer excludes (`test_subsidiary_dimension_alone_does_not_exclude_rows_from_reconciliation`).
- Group-membership audit: `scripts/group_identity_audit.py` -> `docs/group-identity-audit.md` (127 flagged rows =
  33 row-level + 94 group-level; 43 group-level groups + 5 row-level groups = 48; 0 retained HTML-derived fields
  disagree across any group; one HTML row consumed per XBRL row).
- D33 revised: documented reporting-currency evidence required (`test_reporting_currency_override_requires_documented_template_evidence`);
  evidence recorded for Apollo, Goldman Sachs BDC and Stellus.
- Decision pack refreshed: Q1 restated with the concept and period semantics of 17,370,481 (roll-forward ending balance
  of a term loan exported under its schedule member; the "JV" wording withdrawn), stale sequence-pairing recommendation,
  merged-BIP statement and the Barings residual removed, Q3 evidence for every affected period and company.
- Refinement after the first rerun: Crescent's Hercules common-stock row (cost equal to RWA Wealth Partners' cost) was
  flagged contradictory and scoped as a duplicate although the HTML row was matched to its own member; contradictions now
  require an unconsumed HTML counterpart and duplicate scoping requires a sibling without report-date figures (tests extended).
