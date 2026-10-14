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
```

Tested versions are recorded in `docs/progress.md`. No LLM or API key is used by the engine.

### SEC contact for live retrieval

The SEC requires a descriptive User-Agent naming a monitored contact. The engine ships with **no contact
default**: supply one per run or through the environment. Addresses below are placeholders; use a mailbox
you actually monitor.

```bash
# per run (preferred): the User-Agent becomes "[organization] bdc_soi/<version> <email>"
python -m bdc_soi extract --cik 1837532 --latest --output output/run_001 --sec-email analyst@example.com
python -m bdc_soi extract --cik 1837532 --latest --output output/run_001 --sec-email analyst@example.com --sec-organization "Example Research"

# environment alternative (used as given when --sec-email is absent)
export SEC_USER_AGENT="Example Research analyst@example.com"   # Windows: set SEC_USER_AGENT=...
```

Precedence: an explicit `--sec-email` (with optional `--sec-organization`) wins; otherwise `SEC_USER_AGENT`;
with neither, `extract`, `extract-universe` and `inspect` exit with setup instructions before any request.
`--sec-email` and `--sec-organization` are accepted after the subcommand on those three commands only. An empty,
malformed or placeholder address (`example.com`) passed explicitly is rejected rather than ignored. The same
User-Agent is used for filing downloads and for the SEC-hosted taxonomies Arelle retrieves; the contact is never
written to logs, templates or run manifests (the manifest records only `user_agent_source`: cli / environment /
config / none). Offline runs (`--offline`), `--help` and the commands that do not retrieve filings need no contact.

## Commands

```bash
python -m bdc_soi validate-templates --templates templates
python -m bdc_soi inspect --cik 1837532 --accession 0001193125-26-341358 --output output/inspection --sec-email analyst@example.com
python -m bdc_soi extract --cik 1837532 --latest --output output/run_001 --sec-email analyst@example.com
python -m bdc_soi extract --cik 1837532 --accession 0001193125-26-341358 --output output/run_002 --offline
python -m bdc_soi extract-universe --universe config/bdc_universe.yml --output output/run_003 --sec-email analyst@example.com
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
BDC_SOI_LIVE=1 pytest -m live  # live SEC retrieval, needs SEC_USER_AGENT (the live test has no --sec-email)
```

`tests/unit/test_sec_contact.py` covers contact resolution offline: argument precedence, environment fallback,
failure before any request, User-Agent propagation to the SEC client and Arelle, help/offline without a contact,
and the absence of any contact default in runtime code or configuration.

```bash
# security scan of tracked files and history (no secret values are printed)
gitleaks git --redact=100 . && git archive HEAD | tar -x -C /tmp/tracked && gitleaks dir --redact=100 /tmp/tracked
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
