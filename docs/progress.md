# Progress

Last updated: 2026-10-14 (security review and SEC contact runtime configuration, D48; extraction rules unchanged). Resume by reading this file, `docs/coverage-report.md`,
`docs/iteration-log.md` and `docs/decisions.md`. Nothing is committed; all work is in the working tree.

## Environment (tested)
- macOS 15 (Darwin 25.3.0, arm64), project `.venv` with **Python 3.13.9**. Package targets Python 3.11+.
- Windows: supported by design (pathlib, no shell calls, no symlinks) but **not executed** in this project.
- Tested package versions: arelle-release 2.46.0, requests 2.34.2, pandas 3.0.6, openpyxl 3.1.5, beautifulsoup4 4.15.0,
  lxml 6.1.3, PyYAML 6.0.3, pydantic 2.13.5, RapidFuzz 3.14.6, pyarrow 25.0.1, jsonschema 4.26.0, pytest 9.1.1, numpy 2.5.3.
- Install: `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`.
- SEC contact: `--sec-email` per run or `SEC_USER_AGENT` in the shell (genuine contact; never printed, no default in the repository; D48). No LLM/API dependency in the engine.

## Security review and SEC contact (2026-10-14)
- Tracked files and the full reachable history (one commit, `main`, no tags, not shallow) scanned with gitleaks
  8.30.1 (history and a tracked-only export) plus manual pattern review: no credentials, private keys,
  credential-bearing URLs or personal contact addresses found; the single scanner hit is a synthetic fixture date
  string in `tests/fixtures/synthetic/README.md` (false positive). `.gitignore` excludes `.env*`, `cache/`,
  `output/`, `.venv/`, logs and generated annotations. Details: `docs/security-review.md`.
- SEC User-Agent is now runtime configuration (`--sec-email` / `--sec-organization`, else `SEC_USER_AGENT`; D48),
  also applied to Arelle taxonomy downloads; `tests/unit/test_sec_contact.py` (48 offline tests). No extraction
  rule, template or golden data changed; Q1-Q6 remain unapproved; acceptance remains NOT ASSESSED.

## Universe (26 companies, authoritative list from the project owner, verified 2026-10-06)
All 26 CIKs resolve to BDC registrants with eligible 10-Q filings (`output/universe_verification_2026-10-06.json`,
names in `config/bdc_universe.yml`). No invalid CIKs, no unexpected identities. Coverage limitation: Franklin BSP
Real Estate Debt BDC (2018545) has no 10-Q after 2025-06-30 within the 18-month lookback; its latest eligible
filing (0002018545-25-000016, 2025-06-30) and prior 2025-03-31 were processed.

## Baseline (before any session-2 change)
`output/baseline_s2/` holds offline runs of Apollo (3 periods) and Audax (1 period) plus `state_checksums.txt`
(templates, config, every source module) and `pytest_baseline.txt` (115 passed, 1 skipped). Compare with
`python -m bdc_soi compare --before output/baseline_s2/<run> --after <new run> --output <dir>`.

## Implementation status
| Area | Status |
| --- | --- |
| Engine (SPEC 26 steps 1-13, 15, 16) | done, 253 offline tests + 1 live test (skipped offline) |
| Company templates (step 14) | 26/26 companies have evidence-grounded effective-dated templates (`templates/<cik>.yml`), authored from `scripts/template_batches/batch1..4.py` |
| Periods tested per company | latest eligible 10-Q + one prior period (2026-03-31; 2025-03-31 for Franklin BSP; Apollo additionally 2025-06-30 at its effective-date boundary) |
| Refinement (steps 17-18) | failing-test-first fixes recorded in docs/iteration-log.md (iterations 006-027); holdout evaluation NOT ASSESSED |
| Golden data | 52 manifests (`golden/manifests/`), all `review_status: unreviewed`; 52 candidate annotation files exported (`golden/annotations/`); `golden/expected/` empty |

## Results snapshot (engine output; scoped reconciliation, not reviewed accuracy)
Final universe run `output/universe_s3_run17` (26/26 filings ok, 9,107 holdings); determinism run
`output/universe_s3_run18` (`scripts/determinism_check.py`: 18/18 artifacts byte-identical); prior periods `output/s3i_final_<cik>_<accession>`
(26, now including Audax 0001193125-26-219725 retrieved live on 2026-10-06); Apollo's 2025-06-30 run is an additional
historical test outside the 52-filing count. Authoritative matrix: `docs/coverage-matrix.md`
(+ `output/universe_s3_run17/coverage_matrix.csv`), company status = worse of its two periods.
Reconciliation is **scoped** (D43): every exported row carries `reconciliation_scope`, `scope_rule` and
`scope_evidence`; the status compares the in-scope rows with the reported total and `complete_status` compares the
complete exported sum; cash-equivalent positions printed after the grand total are kept in the output and reported
separately. Latest period fair value (scoped) 24 pass / 2 fail (PIMCO, West Bay), cost 24 pass / 2 fail (PIMCO, West Bay); prior period fair value 23 pass / 3 fail (Barings prior period, PIMCO, West Bay), cost 24 pass / 2 fail (PIMCO, West Bay);
complete-exported fair-value status 14 pass / 12 fail in each period (the 12 differ from the scoped result by cash-equivalent positions printed after the grand total, listed per row in the bridge, plus BIP's contradictory-identity duplicate). Company status: 23 companies reconciled (scoped) in both periods, 3 fail in at least one period; 52 filings export 18,236 rows: 18,200 schedule, 29 cash-equivalent-after-total, 6 after-total-section kept in scope (Audax), 1 contradictory-identity duplicate (BIP); 17,817 of them carry a fair value and the bridge publishes both counts (D47). Identity acceptance is BLOCKED for BIP 2026-06-30 (unresolved contradiction, D46) although its scoped reconciliation passes.
- Separate categories (never merged): scoped reconciliation within tolerance; complete-exported status; unresolved
  identity-level conflicts (unmatched, ambiguous, contradictory-identity, unit-mismatch, group-level rows: kept and
  flagged); field-level disagreements classified formatting / identity / semantic / numeric; implementation assumptions
  awaiting approval (`docs/decision-pack.md`, Q1-Q6); independently assessed accuracy (NOT ASSESSED everywhere).
- Session-5 corrections (iteration 026, D43-D45): scope terminology and row-level scope; Audax prior period added and
  template range extended; BIP contradictory identity never merged (both candidates flagged); TriplePoint affiliation
  no longer written into investment_type; 127 sequence-tiebreak rows audited and group-level identity recorded where
  row identity is not demonstrable; conflict classes; `unresolved` review outcome; workbook exposes reporting currency,
  original XBRL unit and principal currency separately with correction fields and decision-case rows.
- Session-6 corrections (iteration 027, D33 revised, D46, D47): identity acceptance separated from numerical
  reconciliation (BIP blocked; both candidates kept, canonical candidate from sibling-member evidence); all-row and
  with-field scope counts; explicit default scope rules; a subsidiary dimension alone no longer excludes; group-membership
  audit `docs/group-identity-audit.md`; documented reporting-currency evidence required and recorded for Apollo, Goldman
  Sachs BDC and Stellus; decision pack refreshed (Q1 restated as the roll-forward ending balance of a term loan).
- Every excluded XBRL candidate is recorded in `excluded_candidates.csv` with its rule and evidence and listed on the
  workbook's `excluded_candidates` sheet; no record is removed to force a total.

## Clarifications acknowledged by the project owner (2026-10-06)
- Row populations: core 52 filings 18,236 exported rows / 17,817 with fair value (gap 419); Apollo historical
  0000950170-25-105984: 707 / 680 (gap 27); combined 53 filings 18,943 / 18,497 (gap 446). The bridge's published
  counts equal the exported counts in both populations.
- Documented reporting-currency overrides: 27 in the core filings (Apollo 8 + 8, Goldman Sachs BDC 5 + 3, Stellus 3)
  plus 16 in the Apollo historical filing = 43; all carry `documented_evidence`.
- Stellus cost/fair-value currency evidence beyond the par footnote and the `$` symbol: Note 2 "The accounting records
  of the Company are maintained in U.S. dollars." and "Foreign currency amounts are translated into U.S. Dollars on the
  following basis: fair value of investment securities, other assets and liabilities, at the spot exchange rate on the
  last business day of the period ..."; the USD undimensioned total (419,527,201) includes the three EUR-tagged rows.
- Q1: the CO Acquisition Vehicle term loan is retained as a holding (fair value 17,370,000, cost 16,310,000,
  table_9 row t9r10); only its second representation, the affiliate roll-forward ending balance 17,370,481
  (F_c6981e7b-5f10-44f7-b1fe-a931faf74745), is an excluded candidate; both values and the 481 rounding difference
  are preserved in the artifacts.
- The acknowledgement does not approve Q1-Q6, golden annotations or further extraction-rule changes.

## Implementation freeze and local checkpoint (2026-10-06)
- Code state: `src/bdc_soi` at the end of iteration 027 (decisions through D47); 253 offline tests pass, 1 live test
  skipped offline; 27 templates validate; template JSON schema regenerated.
- Latest runs (local, not in Git): `output/universe_s3_run17` (latest periods, 26 filings), `output/universe_s3_run18`
  (determinism twin, 18/18 artifacts identical), `output/s3i_final_<cik>_<accession>` (26 prior periods + Apollo
  2025-06-30 historical). Reports generated from them: `docs/coverage-report.md`, `docs/coverage-matrix.md`
  (+ `output/universe_s3_run17/coverage_matrix.csv`), `docs/group-identity-audit.md`, `docs/decision-pack.md`.
- Review artifacts (local): `output/review/review_batch_2026-10-06_triage_v3.xlsx` (200 rows),
  `output/review/blocker_inventory_2026-10-06_v3.csv` (13,731 rows); earlier workbooks preserved. Candidate
  annotations `golden/annotations/*.candidates.csv` (53 files) are engine output, kept on disk and excluded from Git;
  regenerate with `python -m bdc_soi annotate --actual <run> --golden golden --accession <acc>`.
- Not in Git (kept on disk): `cache/` (SEC filing packages, submissions, Arelle taxonomies), `output/`, `.venv/`,
  `.env*`, `golden/annotations/`.
- Unresolved: decision questions Q1-Q6 (`docs/decision-pack.md`, none approved); BIP 0001193125-26-339708 acceptance
  blocked by an unresolved identity contradiction; PIMCO and West Bay scoped reconciliation fails (equal-valued groups
  without descriptions, Q5); Barings prior period fails (duplicate typed members and JV members, Q6); all 53 golden
  manifests unreviewed; production acceptance NOT ASSESSED.
- Next action: a user-run extraction trial from cache (commands in the handoff message); no further development until
  requested. If the trial surfaces a problem, explain it first and wait for instructions before changing code.

## Review package (human review not started)
- Preserved earlier workbooks: `output/review/review_batch_2026-10-06.xlsx` (1,382 rows, session-3 runs) and
  `output/review/review_batch_2026-10-06_triage.xlsx` (144 rows, session-4 runs; superseded).
- Current triage batch (final runs): `output/review/review_batch_2026-10-06_triage_v3.xlsx` (200 rows: 2 ordinary
  rows per company/period, 40 representative blockers, plus decision-case rows for Q3-Q6, group-level identity,
  contradictory identity and both scope rules; `excluded_candidates` sheet for Q1/Q2). A triage and annotation set,
  not evidence for production acceptance.
- Complete blocker inventory (unsampled): `output/review/blocker_inventory_2026-10-06_v3.csv` (13,731 rows, including BIP's XBRL counterpart e6e2ce8c08e96f0136b09e8829ef102c).
- Import: `python -m bdc_soi import-review --workbook <file> --golden golden` (approve / correct / reject /
  unresolved; unresolved rows go to `golden/review_log/`, never to `golden/expected`). Nothing is marked reviewed;
  all manifests stay `unreviewed`; development / regression / holdout assignments unchanged.

## Apollo unit issues (investigated against the instances)
- Non-USD fair-value facts: HTML-confirmed reporting currency rule (decisions D24); rows keep
  `xbrl_fair_value_unit_mismatch` flags; no value converted.
- Percent-unit spread facts (Q1 2026, `decimals=2`): preserved as flagged (`spread_out_of_bounds`,
  `composite_conflict`); never rescaled.

## Acceptance (SPEC 19.6)
**NOT ASSESSED.** No reviewed golden observations exist. Candidate annotations are engine output awaiting a
human reviewer. Reconciliation outcomes above are necessary, not sufficient, evidence of correctness.

## Blockers / pending human input
1. Answer the six questions in `docs/decision-pack.md` (Q1-Q6) before further rule changes; Q4-Q6 include
   implementation changes that are ready to build once approved.
2. Review the triage batch and import it; acceptance stays NOT ASSESSED until reviewed observations exist.
3. Filer inconsistencies kept as flags: Apollo spread units, Muzinich fair-value facts tagged `pure`, Barings
   `| Funded` re-tagging (excluded by template with evidence); BIP `CareSave`/`Integrative Life` label disagreement;
   Jefferies zero-value revolver tagged twice (ambiguous).
4. Windows execution has not been performed.

## Exact next commands
```bash
.venv/bin/python -m bdc_soi validate-templates --templates templates
.venv/bin/python -m bdc_soi extract-universe --universe config/bdc_universe.yml --output output/universe_s3_run19 --offline
# live retrieval needs a monitored contact: add --sec-email <monitored address> (or export SEC_USER_AGENT) and drop --offline
.venv/bin/python -m bdc_soi compare --before output/universe_s3_run17 --after output/universe_s3_run19 --output output/comparison_universe
.venv/bin/python scripts/determinism_check.py output/universe_s3_run17 output/universe_s3_run19
.venv/bin/python scripts/coverage_report.py output/universe_s3_run19 --determinism output/universe_s3_run18
# after reviewer approval into golden/expected with review_status: reviewed:
.venv/bin/python -m bdc_soi evaluate --actual output/universe_s3_run19 --golden golden --report output/universe_s3_run19/evaluation
```
