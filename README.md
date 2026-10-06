# BDC SOI extraction engine

Deterministic, source-grounded extraction of security-level Schedule of Investments (SOI) data from
BDC Form 10-Q filings (XBRL, Inline XBRL and rendered HTML) with effective-dated company templates.
Requirements: `SPEC.md`. Decisions: `docs/decisions.md`. Progress and evidence: `docs/progress.md`,
`docs/iteration-log.md`.

## Setup (macOS / Windows, Python 3.11+)

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -e ".[dev]"
export SEC_USER_AGENT="Your Organization monitored-contact@your-domain"   # Windows: set SEC_USER_AGENT=...
```

Tested versions are recorded in `docs/progress.md`. No LLM or API key is used by the engine.
Live SEC requests require a genuine monitored contact in `SEC_USER_AGENT`; the example address is rejected.

## Commands

```bash
python -m bdc_soi validate-templates --templates templates
python -m bdc_soi inspect --cik 1837532 --accession 0001193125-26-341358 --output output/inspection
python -m bdc_soi extract --cik 1837532 --latest --output output/run_001
python -m bdc_soi extract --cik 1837532 --accession 0001193125-26-341358 --output output/run_002 --offline
python -m bdc_soi extract-universe --universe config/bdc_universe.yml --output output/run_003
python -m bdc_soi evaluate --actual output/run_002 --golden golden --report output/run_002/evaluation
python -m bdc_soi compare --before output/run_001 --after output/run_002 --output output/comparison
python -m bdc_soi annotate --actual output/run_002 --golden golden --accession 0001193125-26-341358
python -m bdc_soi review-package --runs output/run_002 --output output/review/review_batch.xlsx
python -m bdc_soi import-review --workbook output/review/review_batch.xlsx --golden golden
```

Reconciliation is computed on the complete exported output (`reconciliation_bridge.csv`: matched, XBRL-only,
HTML-only, after-total and subsidiary sums against the selected reported total and its source location);
`excluded_candidates.csv` lists holding-axis members that are not canonical holdings together with the rule and
evidence. The human-review workflow (workbook, validated import, sample-scoped evaluation) is described in
`golden/README.md`.

`--offline` uses cached filings and cached Arelle taxonomies only. Output directories are never
overwritten unless `--force` is passed.

## Tests

```bash
pytest                         # offline unit + integration tests on synthetic fixtures
BDC_SOI_LIVE=1 pytest -m live  # live SEC retrieval, needs SEC_USER_AGENT
```

## Universe and coverage

`config/bdc_universe.yml` lists the 26-company project universe (registrant names verified against the SEC
submissions API). Every company has an effective-dated template in `templates/<cik>.yml` whose rules cite the
inspected filings; `docs/coverage-report.md` records per-company periods tested, reconciliation outcomes,
review items and support status: *reconciled on tested periods (scoped)*, *provisional* (unresolved
conflicts such as unmatched rows or unit mismatches remain visible) or *blocked*. Reconciliation covers the complete
exported holdings (`reconciliation_bridge.csv`), is engine self-consistency only, and is kept separate from
independently measured accuracy, which is NOT ASSESSED until human-reviewed expected data exists (`golden/README.md`).

`docs/coverage-matrix.md` (from `scripts/coverage_matrix.py`) lists every company and period with its reconciliation,
unresolved-conflict, pending-approval and accuracy columns kept separate; `docs/decision-pack.md` lists the
interpretations that need the project owner's approval. `review-package --profile triage` builds a small first review
batch and `--blocker-inventory` writes the complete list of flagged rows.

Development helpers under `scripts/` (not part of the engine): `analyze_inspection.py`, `template_evidence.py`,
`run_summary.py`, `triage_run.py`, `write_templates.py` (+ `template_batches/`), `coverage_report.py`, `coverage_matrix.py`.

## Layout

`src/bdc_soi/` engine modules (see `docs/implementation-plan.md`), `templates/` effective-dated
company templates plus `generic.yml`, `config/` application config, universe and JSON schema,
`golden/` manifests/expected/annotations, `tests/` offline tests and synthetic fixtures.
`cache/` and `output/` are local and ignored by Git.
