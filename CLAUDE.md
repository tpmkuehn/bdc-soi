# BDC SOI project instructions

Read SPEC.md before implementation. It defines the requirements; CLAUDE_CODE_PROMPT.md is the initial build task.

- Python 3.11+, src layout (`src/bdc_soi`), macOS and Windows, portable paths (pathlib only).
- Deterministic source-grounded extraction; no runtime LLM requirement.
- Keep company logic in effective-dated templates (`templates/<cik>.yml`), with field-level provenance.
- Use environment variable SEC_USER_AGENT for a monitored SEC contact; never log or persist it.
- Never read or expose API secrets; never commit secrets, .venv, cache, or output.
- No invented filing facts, golden approvals, override provenance, or results.
- Test offline by default (`pytest`); live tests are `@pytest.mark.live` and need `BDC_SOI_LIVE=1`.
- Follow SPEC section 20 for fixes: classify the failure, add a failing test, narrowest remedy, rerun, log in docs/iteration-log.md.
- Preserve run artifacts (never reuse a non-empty output dir without --force); never modify reviewed golden labels to make tests pass.
- Record decisions in docs/decisions.md, progress in docs/progress.md, iteration evidence in docs/iteration-log.md.
- Do not call the application production-ready without measured acceptance on reviewed data.

## Working notes
- Install: `.venv/bin/pip install -e ".[dev]"`; run `.venv/bin/python -m bdc_soi ...`.
- Regenerate the template JSON schema after changing `templates.py`: `python -m bdc_soi validate-templates --write-schema`
  (a test asserts the committed schema matches the model).
- Synthetic fixture (not a real filing): `tests/fixtures/synthetic/`; company template for it in `tests/fixtures/synthetic/templates/`.
- Arelle taxonomy cache lives in `cache/arelle`; offline reruns need it populated by one online run.
- Templates are authored from `scripts/template_batches/batch*.py` via `python scripts/write_templates.py batchN` (keeps evidence strings next to rules); edit the batch module, not the YAML directly, then validate.
- Per-company evidence and triage: `scripts/template_evidence.py`, `scripts/triage_run.py`, `scripts/run_summary.py`; coverage report: `scripts/coverage_report.py output/<universe run>`.
- Company-by-period matrix: `scripts/coverage_matrix.py output/<universe run> <prior-run tag>`; open interpretation questions live in `docs/decision-pack.md` (never describe them as resolved).
- Baseline for regression comparisons: `output/baseline_s2/` (not committed; state checksums inside).
- Reconciliation status is scoped at row level (D43: `reconciliation_scope` with rule and evidence; `complete_status` alongside); matched-only sums are diagnostics. Never remove a record to make a total reconcile; record exclusions with evidence (D32, `excluded_candidates.csv`).
- Human review: `review-package` -> reviewer fills the workbook -> `import-review`; never set review_status yourself (golden/README.md).
