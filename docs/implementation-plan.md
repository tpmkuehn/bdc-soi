# Implementation plan: BDC SOI extraction engine

Date started: 2026-10-06. Requirements authority: `SPEC.md` (26 sections plus conversion notes).
Environment: macOS (Darwin 25.3, arm64), project `.venv` with Python 3.13.9 (spec requires 3.11+; code targets 3.11+ syntax).
Windows is supported by design (pathlib, no shell dependencies) but has **not** been executed on Windows in this project.

Status (2026-10-06): every row below is implemented with offline tests; live retrieval is covered by `tests/integration/test_live_sec.py` (1 passed). Company templates exist for all 26 universe CIKs (`templates/*.yml`, authored from `scripts/template_batches/`); label-format regression tests exist for Apollo and Audax under `tests/regression/`, and the other 24 are exercised by the recorded universe and prior-period runs (docs/coverage-report.md). Production acceptance is NOT ASSESSED (no reviewed golden data) — see docs/progress.md.

## Sequence (SPEC 26) and requirement-to-module checklist

| # | Requirement (SPEC ref) | Module(s) | Tests |
| --- | --- | --- | --- |
| 1 | Typed config, env override for SEC user agent (7.1, 4.3) | `config.py` | `tests/unit/test_config.py` |
| 1 | Canonical holding model, lineage JSON, diagnostics (9.x) | `models.py` | `tests/unit/test_models.py` |
| 1 | Template schema, validation rules, effective-date selection (8.x) | `templates.py`, `config/template.schema.json` | `tests/unit/test_templates.py` |
| 1 | CLI: extract, extract-universe, inspect, validate-templates, evaluate, compare (6.x) | `cli.py`, `__main__.py` | `tests/unit/test_cli.py` |
| 2 | SEC client: UA, shared rate limit, retries 429/5xx, cache, offline (4.3) | `sec_client.py` | `tests/unit/test_sec_client.py` |
| 2 | Filing discovery incl. older submission files, selection log (10.1) | `filing_discovery.py` | `tests/unit/test_filing_discovery.py` |
| 2 | Package retrieval, checksums, instance detection by root element (10.2) | `filing_package.py` | `tests/unit/test_filing_package.py` |
| 3 | Arelle loading, taxonomy cache, offline rerun (11, 22.3) | `xbrl_loader.py` | `tests/integration/test_xbrl_synthetic.py` |
| 3 | Fact inventory, semantic dates, dimension serialization (11.1, 11.2) | `xbrl_inventory.py` | `tests/unit/test_xbrl_dates.py`, `test_xbrl_inventory.py` |
| 3 | Concept mapping precedence (11.3) | `concept_mapping.py` | `tests/unit/test_concept_mapping.py` |
| 3 | SOI role discovery (11.4) | `role_discovery.py` | `tests/unit/test_role_axis.py` |
| 3 | Holding-axis scoring and selection (11.5) | `axis_discovery.py` | `tests/unit/test_role_axis.py` |
| 3 | Grouping, duplicate selection, conflicts (11.6, 11.7) | `xbrl_holdings.py` | `tests/unit/test_xbrl_holdings.py` |
| 4 | HTML table scoring, headers, scale, rows, carry-forward, numeric parsing (12.x) | `html_tables.py` | `tests/unit/test_html_tables.py` |
| 5 | Composite parsing, rate parsing, industry prefix, dates (13.x) | `composite_parser.py` | `tests/unit/test_composite_parser.py` |
| 5 | One-to-one XBRL/HTML matching with margins (14.x) | `hybrid_matcher.py` | `tests/unit/test_hybrid_matcher.py` |
| 5 | Normalization, lineage, holding ID, dedup (9.4, 15.x) | `normalization.py`, `identity.py` | `tests/unit/test_composite_parser.py`, `test_identity_validation.py` |
| 6 | Reconciliation, validation rules, confidence, review flags (16, 17, 18.2) | `validation.py`, `confidence.py` | `tests/unit/test_identity_validation.py` |
| 6 | Output artifacts, manifest, Excel/CSV/Parquet/JSON (18.x) | `output.py`, `diagnostics.py` | `tests/integration/test_pipeline_synthetic.py` |
| 6 | Evaluator: golden manifests, alignment, metrics, thresholds (19.x) | `evaluation.py`, `golden/` | `tests/integration/test_pipeline_synthetic.py` |
| 6 | Run comparison (6.5, 20 step 5) | `compare.py` | `tests/integration/test_cli_and_compare.py` |
| 6 | Pipeline orchestration with phase-isolated failures (23) | `pipeline.py` | `tests/integration/test_pipeline_synthetic.py` |
| 7 | Company templates from real filing evidence (8, 22.4) | `templates/1837532.yml`, `templates/1633858.yml` | `tests/regression/test_apollo_template_rules.py`, `test_audax_template_rules.py` |
| 7 | Iteration protocol evidence (20, 21) | `docs/iteration-log.md` | — |

## Required unit tests (SPEC 22.1) mapping

CIK normalization → `test_sec_client.py`; SEC URL construction → `test_sec_client.py`; instance-document detection → `test_filing_package.py`;
semantic XBRL dates → `test_xbrl_dates.py`; QName extraction → `test_concept_mapping.py`; concept mapping precedence → `test_concept_mapping.py`;
context dimension serialization → `test_xbrl_inventory.py`; holding-axis scoring → `test_axis_discovery.py`; duplicate fact selection → `test_xbrl_holdings.py`;
HTML monetary parsing, percentage parsing, scale detection, multi-row header flattening, total-row detection, issuer carry-forward, industry heading → `test_html_tables.py`;
composite issuer parsing, reference-index aliasing, spread conversion, date normalization → `test_composite_parser.py` (includes exact Redwood example, 22.2);
XBRL/HTML match scoring, ambiguous match rejection → `test_hybrid_matcher.py`; reconciliation status → `test_validation.py`;
deterministic holding ID → `test_identity.py`; template overlap rejection → `test_templates.py`.

## Integration tests (SPEC 22.3)

Offline (synthetic fixture instance + HTML under `tests/fixtures/synthetic/`): Arelle load, inline fallback, SOI table extraction, holdings + validation output, cached rerun determinism.
Live (`@pytest.mark.live`, skipped unless `BDC_SOI_LIVE=1` and `SEC_USER_AGENT` set): retrieve and cache a real accession, full extract, rerun from cache.

## Semantic decisions to fix explicitly (see docs/decisions.md)

- total_if_regex evaluated before skip_if_regex; totals retained for reconciliation, excluded from holdings.
- Concept references: Clark `{uri}Local` exact; `prefix:Local` resolved by namespace family; bare `Local` is a local-name fallback tier; `{issuer-namespace}` placeholder rejected in production templates.
- `issuer_name`/`security_description` accepted as template aliases; output exposes `issuer`/`description`.
- `spread` stored as decimal, `spread_bps` as basis points; `spread_output_format` only affects Excel display.
- Percent-formatted spreads parsed by a percent branch, never the bps branch.
