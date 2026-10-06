Read @SPEC.md and @CLAUDE.md completely before making changes. Implement the BDC Schedule of Investments Extraction Engine described in SPEC.md in this repository. The existing files are starter scaffolding, not a completed application. Write working code and run meaningful checks; do not stop after a plan or leave successful-looking placeholder commands.

Context and boundaries:
- I am developing on a MacBook using Claude Code with Anthropic API billing. Support macOS and preserve the specification's Windows support. Use Python 3.11+ and a src-layout package.
- The Anthropic API key authenticates Claude Code. Do not add LLM calls, an Anthropic SDK dependency, or API-key requirements to the extraction engine. Version 1 must be deterministic for the same filing package, templates, engine version, and configuration.
- Treat SPEC.md as the requirements authority, including its explicitly labelled conversion notes. Preserve its original requirements. Record justified implementation choices in docs/decisions.md. Ask only where missing information prevents a correct decision; proceed with all independent work.
- Do not read, print, persist, or commit secrets. Use SEC_USER_AGENT from the environment for SEC requests, requiring a genuine monitored contact before live retrieval. Do not use the example email address. Keep credentials, .venv, cache, output, and machine-local settings out of Git.

Start by inspecting this repository, reading the specification, and identifying the environment. Create docs/implementation-plan.md with a requirements-to-module/test checklist, then immediately begin implementation. Maintain CLAUDE.md as a concise project guide and docs/progress.md so work can resume across sessions. Use the project .venv. Select compatible dependencies, install the package in editable mode, record the tested Python and package versions, and provide reproducible dependency installation instructions. Add __main__.py so python -m bdc_soi works.

Implement in the sequence in SPEC section 26, in testable increments:
1. Typed configuration and canonical models; formal template schema and effective-date selection; all six CLI commands: extract, extract-universe, inspect, validate-templates, evaluate, compare.
2. SEC filing discovery, compliant shared rate limiting, bounded retries/backoff, accession package discovery, checksums, cache reuse, and offline operation. Never fetch illustrative all-zero accessions. Discover and record real metadata.
3. Arelle instance/Inline XBRL loading, complete fact inventory, semantic dates, concepts, roles, dimensions, holding-axis selection, deterministic grouping, duplicate selection, and conflict diagnostics.
4. HTML SOI identification and table reconstruction, period filtering, headers, row classification, carry-forward boundaries, monetary units/scales, totals, raw values, and source locations.
5. Composite parsing, one-to-one XBRL/HTML matching, normalization, field-level lineage, deterministic holding identity, and conservative deduplication.
6. Reconciliation, confidence factors, review queues, complete output artifacts, manifests, Excel/CSV/Parquet/JSON export, evaluation, and run comparison.
7. Company-specific effective-dated templates grounded in actual filing evidence, regression refinement, and holdout evaluation when reviewed data is available.

Correctness requirements:
- Preserve security/facility identity; never collapse instruments just because issuer and monetary values match. Preserve classification dimensions as lineage.
- Do not infer undisclosed issue dates or rewrite issuer/security meanings. Never invent facts, override provenance, reviewer identities, filing accessions, golden labels, or test results.
- Export issuer and description consistently. Store spread as a decimal rate, spread_bps as basis points, and monetary fields in correctly scaled filing-currency units. Test 450 bps = 0.045 and 0.50% floor = 0.005. Test percent-formatted spreads separately from basis-point text.
- Fix the illustrative template's semantic ambiguities explicitly, including total/skip precedence, exact namespace versus local-name matching, alias names, and display versus storage units. Do not enable placeholder templates as production mappings.
- Match the current reporting period and compatible currencies/units before reconciling. Treat ambiguous matches/totals as unresolved with diagnostics. Isolate affected records for review while continuing independent filings.
- If XBRL fails, retain HTML fallback; if HTML fails, retain XBRL results. Invalid templates fail before extraction. A filing failure must not terminate the entire universe.
- Never catch and suppress an exception without filing/phase diagnostics. Preserve prior run artifacts.

Testing and evidence:
- Implement the tests required by SPEC section 22, including the exact Redwood composite example, Arelle semantic dates, ambiguous matches, total exclusion, scale conversion, effective-date boundaries, repeated issuer facilities, and deterministic cached reruns.
- Keep routine tests offline with clearly labelled synthetic or documented fixtures. Mark live integration tests explicitly. Cache Arelle taxonomy dependencies needed for an offline rerun, not just the filing HTML.
- For each extraction defect, identify its failure category, add and observe a failing test, apply the narrowest generic/template remedy, then rerun the affected case and full applicable regression suite. Record evidence in docs/iteration-log.md.
- The supplied specification contains no reviewed golden corpus or final company universe. Use its example CIKs only as provisional development targets; verify their SEC identities and eligible filings. Do not claim support for 25–30 BDCs from those examples alone.
- Implement golden manifests, annotations, development/regression/holdout separation, and all specified metrics. Candidate annotations are unreviewed until a human approves them. Synthetic tests do not establish real-filing production accuracy. Never alter reviewed expected outputs to make tests pass or tune against holdout labels.
- First prove an end-to-end run on one verified filing, then expand to another company and different periods. If live access or human review is blocked, finish all feasible implementation and offline checks, record the exact blocker, and report acceptance thresholds as NOT ASSESSED where applicable.

Before finishing, run all available applicable checks, validate templates, inspect/extract a verified accession if live access is configured, produce all required artifacts, and rerun from cache to check determinism excluding operational timestamps. Document any other nondeterministic metadata explicitly; do not weaken normalized-output determinism. Do not claim Windows execution was tested unless it actually was.

Deliver a concise completion report with implemented requirements, commands actually executed, pass/fail/skip results, output paths, selected CIKs/accessions, reconciliation findings, measured evaluation metrics, pending human review, known unsupported formats, and exact next commands. Distinguish implementation completion from production acceptance. Start now.
