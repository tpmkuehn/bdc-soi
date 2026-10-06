# Implementation decisions

Each entry records a choice that SPEC.md leaves open (or that its illustrative examples make
ambiguous) and why it was made. Numbered requirements were not weakened.

## D1. Python 3.13 in the project venv; code targets 3.11+
The machine's `.venv` is Python 3.13.9. The package declares `requires-python >= 3.11` and uses no
3.12+ syntax. Tested versions are in `docs/progress.md`. Windows execution has not been performed.

## D2. Concept references: Clark, prefixed, bare local name
`{uri}Local` is an exact Clark QName. `prefix:Local` is exact on the local name within a namespace
*family* (regex over the namespace URI, e.g. `us-gaap` matches any `http://fasb.org/us-gaap/YYYY`),
because taxonomy namespaces change yearly and a Clark name would silently stop matching. The pseudo
prefix `issuer` resolves at load time to the instance's extension namespace(s). A bare local name is
a controlled fallback tier (`template_local` / `generic_local`) ranked below exact references and
above regex. The example `{issuer-namespace}` placeholder is rejected unless the template is marked
`status: placeholder`, and placeholder templates are never selected for extraction.

## D3. Total/skip precedence in HTML row rules
Row classification order: `total_if_regex` -> `subtotal_if_regex` -> `skip_if_regex` -> footnote ->
repeated header -> holding -> group heading. A total/subtotal row is retained as a reported-total
candidate for reconciliation and excluded from holdings. The example overlap (`^Total` in skip and
`Total Investments` in total) is therefore resolved: the total row is classified first. Identical
patterns in both lists are rejected by validation (SPEC 8.4 "row rule conflicts with total rule").

## D4. Field aliases and export names
Templates may use `issuer_name` / `security_description`; they are canonicalized at validation time
to `issuer` / `description`, which are the only names exported. Override match key `raw_issuer_name`
is an alias of `issuer_name_raw`.

## D5. Spread storage and display
`spread` is a decimal rate (0.045), `spread_bps` basis points (450). `spread_output_format` only
adds a `spread_display` column in `output.xlsx`. A spread capture followed by `%` is parsed on the
percent branch even if the template's capture group is named `spread_bps`, and a diagnostic is
recorded. With `spread_unit: auto`, the rule is "percent if a `%` sign follows, else basis points";
a capture group named plainly `spread` requires an explicit unit (validation error otherwise).

## D6. Reference-index aliases
Only unambiguous tokens (SOFR, LIBOR, Prime, EURIBOR, ...) resolve generically. Single letters
(S, L, P, E, C, B) resolve only through a company template's `index_aliases`, which must cite
supporting evidence (for Apollo: the filing's own SOFR extensible-enumeration facts).
XBRL extensible-enumeration values (`...#SecuredOvernightFinancingRateSofrMember`) are normalized by
a fixed alias table (`normalize_reference_index_enum`).

## D7. Template selection and overlap validation
Selection follows SPEC 8.1 exactly (accession-specific -> narrowest range -> highest priority ->
error). Validation rejects two non-placeholder templates whose date ranges and forms overlap when
neither is accession-specific, their range widths are equal and their priorities are equal, since
selection could not resolve them.

## D8. Holding identity and deduplication
`holding_id` = first 32 hex chars of SHA-256 over `cik|accession|member:<holding-axis member>` (or
`row:<table:row>` for HTML-only rows). Deduplication merges only identical source identities;
rows that agree on issuer, description, maturity, principal, cost, fair value, spread and index
across different source identities are flagged `possible_duplicate_strong_fields` for review,
never merged automatically.

## D9. Currency handling
`currency` is the unit of the principal/face fact (instrument currency), else the only monetary
unit in the holding. `reporting_currency` (lineage column) is the unit of the selected fair-value
fact. Reconciliation compares XBRL total candidates to the reporting currency; filings whose
holdings have several reporting currencies get `review` status and a filing flag. Different
instrument currencies under a single reporting currency do not block reconciliation
(flag `mixed_instrument_currencies_single_reporting_currency`).

## D10. Reported-total ranks (SPEC 16.1)
0 template XBRL total concept, 1 undimensioned XBRL fact, 2 company-template HTML total row,
3 generic HTML total row, 4 XBRL fact with only classification dimensions, 5 HTML subtotal.
Equally ranked candidates whose values differ beyond tolerance produce `ambiguous_total`.
When all rows fail but XBRL/hybrid rows alone reconcile, status is `review` with a note that
appended unmatched HTML rows inflate the detail sum.

## D11. Group-heading levels in HTML tables
A heading row equal to a classification value disclosed in the instance (industry, investment type,
affiliation members) is assigned to that field. If the industry vocabulary is known and a heading is
not in it, the heading is treated as an issuer-level heading rather than overwriting the industry
(observed layout: Apollo Debt Solutions). Templates can force targets with `group_heading_rules`
and `group_heading_target`.

## D12. Combined "Par/Shares" columns
A header matching both Par/Principal and Shares/Units maps to an internal `principal_or_shares`
column. Per row, equity-like descriptions without maturity/rate evidence yield `shares` (unscaled);
otherwise the value is `principal_amount` (scaled). The choice is recorded in the row notes.

## D13. HTML rate text in an "Interest Rate" column
If a cell mapped to the numeric `interest_rate` column is non-numeric text (e.g. `S+425, 0.50% Floor`)
it is stored as `interest_rate_text` and parsed by the template's rate parser.

## D14. Output directory protection and determinism
`extract`/`inspect` refuse to write into a non-empty output directory unless `--force` is given,
preserving prior run artifacts. `run_manifest.json` lists its operational fields (`run_id`,
`started_at`, `finished_at`, `git_commit`, `platform`) as nondeterministic; everything else, including
`output.xlsx` (fixed document timestamps), is byte-identical across cached reruns.

## D15. Composite parsing precedence
Composite rules operate on the raw source text (`issuer_name_raw` for the member label). Parsed
values replace fields whose lineage is the same member label; they never overwrite a direct XBRL
fact under `direct_first` (a differing parse is recorded as a field conflict). Unmatched labels get
`composite_no_match:<rule>` and enter the review queue.

## D16. Acquisition dates are not issue dates
`us-gaap:InvestmentAcquisitionDate` is left unmapped by the generic template; `issue_date` is only
populated when a template or reviewed override maps a disclosed issue date.

## D17. Evaluation inputs
Golden manifests carry `review_status`; only `reviewed` manifests count toward acceptance.
`annotate` exports unreviewed candidates with `review_status: unreviewed`; `evaluate` can score them
with `--include-unreviewed` for engineering feedback but still reports acceptance NOT ASSESSED.

## D18. Template industry vocabulary recognised in HTML headings
Composite `known_industries` lists are evidence-grounded (copied from the filing) and are merged with
XBRL classification members when deciding whether a heading row is an industry or an issuer-level heading
(observed: Audax's XBRL industry axis uses different sector names than its HTML headings).

## D19. Heading cleanup and ignore rules
Heading values drop footnote markers, "(Continued)" page-break noise and trailing colons.
`group_heading_rules` may target `ignore` for page headers such as the registrant name.

## D20. Rows after the grand total
HTML rows following a row matched by `total_if_regex` (e.g. cash equivalents after "Total Investments
before Cash Equivalents") are kept as holdings but flagged `html_row_after_total` and excluded from the
reconciliation detail sum, with the exclusion recorded in the reconciliation notes.

## D21. Extensible enumerations and non-monetary XBRL groups
Extensible-enumeration fact values are resolved to member labels (issuer, industry, investment type);
reference-index enumerations go through the alias table. XBRL holding-axis groups with no monetary field
(fair value, cost, amortized cost, principal, face, shares) are not holdings; their count is a filing note
and flag (`xbrl_groups_without_monetary_values_excluded:N`).

## D22. HTML-preferred text fields
`html.prefer_html_fields` lets a template declare fields (Apollo/Audax: issuer) for which the disclosed HTML
cell supersedes a value derived from composite text or a dimension label. A direct XBRL fact is never
superseded; the superseded value is kept as a field conflict with reason `html_preferred_over_derived_text`.

## D23. Filer inconsistencies are flagged, not corrected
Spread facts tagged as 4.50 instead of 0.045, fair-value facts tagged in GBP/CAD while the total is USD,
and labels disagreeing with direct facts are surfaced through `spread_out_of_bounds`, reporting-currency
`review` status and `composite_conflict` flags. The engine never rescales or overrides a disclosed value.

## D24. Reporting-currency confirmation by the HTML cell (Apollo, Goldman Sachs)
A fair-value fact tagged in the instrument currency (GBP/CAD/EUR) with no USD counterpart is treated as
stated in the document currency only when the matched HTML fair-value cell (stated in the document
currency) equals it numerically. No value is converted; the row keeps the flag
`xbrl_fair_value_unit_mismatch:<unit>:html_confirms_<currency>` and the lineage records the tagged unit.
Spread facts tagged in percent units (Apollo Q1 2026, `decimals=2` versus 4 elsewhere) remain flagged
(`spread_out_of_bounds`, `composite_conflict`) and are never rescaled.

## D25. Typed labels that concatenate HTML cells
Most filers build the typed `InvestmentIdentifierAxis` label from the HTML row cells. When the matched
HTML cell text (issuer, description, industry) is contained in the label, the HTML cell supersedes the
label-derived value with reason `html_cell_contained_in_label`; direct XBRL facts are never superseded.
Templates may declare `html.prefer_html_fields` for the same effect without the containment test.

## D26. Non-holding members on the holding axis
Members whose label is an exact total/net-assets phrasing (`Total Investments`, `Net Assets`,
`Liabilities in Excess of Other Assets`, `Investments`) are not holdings; their fair value/cost facts
become total candidates (`xbrl_member_total`). An issuer named "Total Expert Inc." is still a holding.
Members whose label is a prefix of at least two other members and whose value equals the sum of those
members are section nodes (`xbrl_parent_member_excluded`). Members with no monetary field (commitment
schedules) are excluded with a count. Templates may add `row_axes.exclude_member_regex` with mandatory
evidence (Barings `| Funded` re-tagging, Investcorp section aggregates, Muzinich hierarchy nodes).

## D27. Subsidiary and after-total rows in reconciliation
Holdings tagged with a consolidated-subsidiary/legal-entity axis are flagged `xbrl_subsidiary_context`
and excluded from the reconciliation sum with a note. HTML rows listed after the grand-total row (cash
equivalents, money-market funds) carry `html_row_after_total`, also propagated to matched XBRL rows, and
are excluded from the sum. When matched rows reconcile but XBRL-only rows absent from the HTML schedule
exceed the total, the status is `review` with the XBRL-only sum in the notes.

## D28. HTML table reconstruction additions
Single-cell title rows are captions (period/scale evidence), not header rows; adjacent columns sharing an
identical header (Golub's split "Spread Above Index") are merged; roll-forward, non-accrual, unfunded
commitment, investment-activity and risk-rating tables are excluded generically; `Total Investments in
<Money Market Fund>` and `Total Investments and Cash Equivalents` are not the grand total; rows whose
text is only numbers/dashes are subtotals; an issuer named "Total Fleet Buyer, LLC" with a facility, rate
or maturity is a holding; zero-width characters are stripped; heading values drop `(Continued)`,
footnote markers and trailing `- 12.3%` suffixes; templates may `ignore` page-header rows.

## D29. Template vocabularies and evidence-backed overrides
`row_rules.known_industries` and composite `known_industries` are recognised as heading vocabulary even
when the instance's industry axis uses other names (Golub, Audax). `validation.total_source_preference`
re-ranks total sources only with evidence (26North, Muzinich). `validation.allow_negative_fair_value`
requires evidence (unfunded commitments carried at negative fair value). HTML "Amortized Cost" columns are
mapped to `cost` only where the run showed 0 cost conflicts against `us-gaap:InvestmentOwnedAtCost`.

## D30. Composite rule kinds
`kind: delimited` splits a label on a delimiter and assigns positions (Barings, Golub, New Mountain,
SLR, TriplePoint); `kind: regex` remains the default. Rate-like captures (`interest_rate`, `spread`,
`reference_index`) are coerced through the normalization layer; `header_parser.industry_position: infix`
finds a known industry anywhere in the header (BIP Ventures).

## D31. Full-output reconciliation and the bridge (session 3)
The reconciliation status is computed from every exported canonical holding carrying the field, minus only two
evidence-based section exclusions that are themselves reported in the bridge: rows listed after the schedule's
grand-total row (`html_row_after_total`, position evidence) and rows tagged with a subsidiary/legal-entity axis
(`xbrl_subsidiary_context`, dimension evidence). Matched-rows-only sums are a diagnostic
(`matched_only_status`) and never decide a status; the earlier "review because matched rows reconcile" outcome
is withdrawn. `reconciliation_bridge.csv` lists matched, XBRL-only, HTML-only, after-total, subsidiary,
complete-exported and in-scope sums, the selected total with its source location, tolerance, currency and
reporting period.

## D32. Canonical holdings versus excluded candidates
Every holding-axis member that is not exported as a canonical holding is written to
`excluded_candidates.csv` with its label, values, fact and context ids, the rule and its evidence:
template member exclusions (`row_axes.exclude_member_regex`, evidence mandatory), exact total/net-assets labels,
parent nodes equal to the sum of >=2 children, investments-in-affiliates schedule members (roll-forward concepts
such as `InvestmentsInAndAdvancesToAffiliatesAtFairValueGrossAdditions` with no principal/rate/maturity facts;
observed Chicago Atlantic `CO Acquisition Vehicle LLC`, Golub one-part members), and members without any
monetary fact. Nothing is removed without a recorded rule.

## D33. Reporting-currency evidence (revision of D24)
A fair-value fact tagged in a non-document currency is re-assigned to the HTML column's currency only when the
HTML column discloses that currency through a symbol cell (`$`, `£`, `€`, `C$`, ...) at or above the row in the
same accepted page sequence, and the HTML cell equals the fact numerically. Equal values alone, or agreement
with totals alone, are not sufficient: without a disclosed symbol the fact's unit stands and the row carries
`xbrl_fair_value_unit_mismatch:<unit>:no_html_currency_evidence`. The XBRL unit, fact id and value, the HTML
symbol, its source row and value are preserved in a `reporting_currency` field conflict and lineage entry.

## D34. Header-less continuation pages
A table with no header row that immediately follows an accepted schedule page (or whose closest preceding block
is a "(continued)" schedule heading) with the same raw column count inherits that page's column compression
and mapping (`inherited_header_from_<table>`). Observed on Golub Capital BDC, where eight SOI pages carry no
repeated header. Unrelated tables of the same width further down the document are not continuation pages.

## D35. Sequence tie-break and post-total tables
Equal-valued ambiguous groups are matched in document order only when the XBRL and HTML groups have the same size,
identical fair value/cost/principal and pairwise-agreeing descriptions (SPEC 14.2 table sequence); the result is
flagged for review. A headed table with no current-period date that follows the schedule's grand-total row is not
part of the schedule (D27 scope) and is rejected with a recorded reason.

## D36. Page-wrapper blocks are not headings
When walking back from a table to collect its heading text, a preceding block that itself wraps a table is the
previous page (observed on Stellus, Crescent and TriplePoint, whose pages are `<div>` containers holding the title
and the table). Only text after its last nested table is eligible as heading text; the statement inside it
("Change in Unrealized", "Statements of Cash Flows") must not reject the schedule's first page.

## D37. Currency-coded numeric cells
A numeric cell prefixed or suffixed by an ISO currency code (`CHF 19,009`) parses as a number and keeps the code as
currency evidence (D33). A row whose only non-numeric content is currency codes/symbols is a numbers-only row and is
classified as a subtotal (Crescent's unlabelled issuer subtotal `CHF 19,009 $20,657 3.7 $23,763`). The rule is
structural (label-less row) and does not use the arithmetic relation to neighbouring rows.

## D38. Issuer group context is reset by higher-level headings
A heading that sets any field other than `issuer` clears the issuer context inherited from an earlier
lower-level heading. Blank issuer cells under the new group then carry forward from the preceding holding row
when the template enables `carry_forward: [issuer_name]` (TriplePoint, evidence recorded in the template) and
otherwise stay empty rather than receiving an unrelated heading.

## D39. Positional issuer columns must hold text
A leading unmapped column is accepted as the issuer column only when its data cells are predominantly
non-numeric. A positional issuer column whose cells are numbers is a summary table's value column
(Crescent Note 4 "Investments at fair value consisted of the following" with two dated cost/fair value groups); the
mapping is dropped and the table is penalised (`positional_issuer_column_numeric`).

## D40. Footnote cells and location cells in heading rows
Cells holding only footnote markers are not row content when deciding whether a row is a group heading, and an
issuer heading takes its value from the name cell rather than the whole row (Stellus
`Bart & Associates, LLC | (4) | McLean, VA`). A literal `N/A` maturity is not debt evidence for a combined
par/shares column (Onex equity rows carry share counts there).

## D41. Investcorp zero-fair-value equity rows (identity, not value, matching)
Investcorp's equity members use the four-part label with a comma inside the section name ('Equity, Warrants and
Other Investments'), '{Issuer} - {Description}' inside the label and ', Initial Acquisition Date'; the HTML
'Investments' cell carries '{Issuer} - {Description}' and the share count sits in the combined 'Principal Amount/
Shares' column under the equity section heading. The template parses both sides; for a combined par/shares column the
matcher compares the HTML value against the other XBRL quantity as well (`shares_via_combined_column`), because the
HTML side can only guess which quantity the column holds (a section-heading rule was tried and reverted: Commonwealth
tags unit counts as principal); identical normalized issuer names earn an `issuer_exact` matching feature so
near-identical share classes (A-1 vs B-1) resolve. Rows are paired on issuer,
description and share count, never on equal monetary values alone; zero-value holdings are kept.

## D42. Company status is the worse of its periods; triage batch separate from the full batch
`docs/coverage-matrix.md` lists all 52 filings; a company's status is the worse of its two periods so a latest-period
pass never hides a prior-period failure. Reconciliation within tolerance, identity-level conflicts (unmatched,
ambiguous, unit-mismatch, sequence-paired rows), field-level disagreements, implementation assumptions awaiting
approval (`docs/decision-pack.md`) and independently assessed accuracy (NOT ASSESSED) are separate columns. The review
package has a `triage` profile (ordinary rows per period plus round-robin blockers under a global budget) and writes the
complete blocker inventory separately; the full stratified workbook is preserved.

## D43. Row-level reconciliation scope (revision of D27/D31 terminology)
Every exported holding carries `reconciliation_scope`, `scope_rule` and `scope_evidence`. `schedule` rows and
`after_total_section` rows (printed after the grand-total row without cash-equivalent evidence, e.g. Audax's
consolidated-subsidiary equity section that the XBRL total includes) count against the reported total;
`cash_equivalent_after_total` rows (money-market, liquidity, government/treasury funds, T-bills, 'Cash Equivalents',
'Other Cash' printed after the grand-total row) and `subsidiary_context` rows are legitimate positions kept in the
output and reported separately. The reconciliation `status` is therefore a **scoped** result; the bridge also carries
`complete_status` (complete exported sum versus the total) and the row counts per scope. The phrase
"full-output reconciliation" is retired: 20 of 47 earlier passes relied on these exclusions and must be read as scoped.

## D44. Group-level identity for equal-valued groups
A sequence pairing (D35) is row-level only when every description is distinct on both sides and each pair agrees
exactly. Otherwise the rows are paired at group level: each XBRL row still consumes one HTML row (source multiplicity
preserved, no double counting), `identity_resolution = group`, a shared `match_group_id`, the HTML source reference is
the whole group, and HTML-derived fields survive only where every row of the group carries the same value (differing
values are dropped with a `group_members_differ_no_row_identity` conflict). No pairwise lineage is fabricated.
Description-less groups (PIMCO, West Bay; decision Q5) are not paired by this rule.

## D45. Contradictory identity, conflict classes, unresolved reviews
Equal non-zero monetary values with a different issuer (similarity < 75) and a different description are
contradictory identity evidence (zero-value agreement, e.g. unfunded revolvers, is no evidence either way): the candidates are never merged, both sides are exported with
`contradictory_identity_candidate:<counterpart>` and the filing is unsuitable for acceptance until a reviewer decides
(BIP: a CareSave-labelled XBRL member carrying Integrative Life Network's figures). Field conflicts carry a
`conflict_class`: formatting (case, punctuation, legal suffix, '&'/'and', sequence suffix, label containment for name
fields, phrase extension for vocabulary fields), identity, semantic, numeric; raw values stay in the conflict. The
review import accepts `unresolved` (comment required), logged under `golden/review_log/` and never written to
`golden/expected`.

## D33 (revised 2026-10-06). Documented reporting-currency evidence
A fair-value fact tagged in a non-schedule unit is reported in the schedule currency only when the company template
records `validation.reporting_currency_evidence`: filing excerpts citing the accession (schedule footnote defining
currency markers for the par column, accounting-policy note on the reporting currency, the USD undimensioned total
that includes the rows). A column `$` symbol alone never re-assigns the currency: the XBRL unit stands and the row is
flagged `no_documented_reporting_currency_evidence`. Applied with evidence for Apollo (three periods), Goldman Sachs
BDC and Stellus; the original unit stays in `fair_value_unit_original` and in the conflict record.

## D46. Contradictory identity: acceptance versus reconciliation
Numerical reconciliation never resolves identity. Any unresolved `contradictory_identity_candidate` blocks the
filing's acceptance (`acceptance = blocked:...` in the bridge, matrix and report) regardless of tolerance. Both
candidates stay in the output and in the blocker inventory. A canonical candidate is chosen only from source
evidence: when the XBRL instance carries a sibling identifier member naming the HTML row's issuer and description
(BIP: the Integrative Life Network Class A member with December facts and a June acquisition-date fact), the
contradicting XBRL candidate is scoped `contradictory_identity_duplicate` (outside the sums, rule and evidence on
the row); the sibling must itself lack report-date fair-value/cost facts (its gap is what the candidate fills).
Without such evidence both candidates stay in schedule scope so the discrepancy remains visible. An equal-money
HTML row that is consumed by its own XBRL member is a value coincidence, not a contradiction: the XBRL row stays
XBRL-only with `value_coincidence_with_matched_html_row:<row>` (Crescent: Hercules common stock cost equals RWA
Wealth Partners' cost) and acceptance is not blocked.

## D47. Scope counts and the subsidiary dimension
The bridge publishes two scope counts: rows carrying the reconciled field (`scope_rules`) and every exported row
(`scope_rows_all`); the gap (rows without a fair value: unfunded commitments, zero-value positions) is reported, not
hidden. `schedule` rows carry an explicit default rule and evidence. A subsidiary/legal-entity dimension on its own is
not exclusion evidence: such rows stay in scope (`D47:subsidiary_dimension_in_scope_by_default`, flagged) until a
template records evidence that the consolidated total excludes the entity.
