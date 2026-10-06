# Golden dataset

- `manifests/<accession>.yml`: one per filing; `split` (development | regression | holdout), `review_status`
  (`unreviewed` | `reviewed`), `review_scope` (`full` | `sample`), reviewer and review date, expected file.
- `expected/<accession>.csv`: rows written by `python -m bdc_soi import-review` from a filled review workbook.
  Each row has `annotation_id`, `holding_id`, canonical fields, `decision` (approve | correct | reject),
  `reviewer`, `review_date`, `comments`. Nothing in this directory is created without a reviewer's entries.
- `annotations/<accession>.candidates.csv`: UNREVIEWED candidates exported by `python -m bdc_soi annotate`.

## Review workflow (human in the loop)
1. Build the workbook: `python -m bdc_soi review-package --runs <run dirs> --output output/review/review_batch_<date>.xlsx`.
   The `instructions` sheet documents the stratified sampling; `summary` lists company/period reconciliation
   (full-output bridge); `review_batch` holds the candidate rows with proposed values, source text, XBRL units,
   SEC document URLs, table/row/context references, lineage, conflicts and blank reviewer columns.
2. Review rows in the filing; fill `reviewer_decision` (approve/correct/reject), `corrected_*` values when
   correcting, `reviewer_name`, `review_date`. Leave unreviewed rows blank.
3. Import: `python -m bdc_soi import-review --workbook <file> --golden golden`. The import validates every
   decided row (decision vocabulary, name, ISO date not in the future, corrections present for `correct`) and
   rejects the whole workbook with row-level messages on any problem. Accepted rows go to `expected/`, and the
   manifest becomes `review_status: reviewed`, `review_scope: sample`. Splits are never changed.
4. Evaluate: `python -m bdc_soi evaluate --actual <run> --golden golden --report <dir>`. Sample-scoped filings
   are judged on the reviewed holding_ids only; reviewer-rejected rows count as false positives when the engine
   still exports them. The first batch does not establish the SPEC 19.6 thresholds; acceptance stays NOT
   ASSESSED until enough reviewed rows exist per company and holdout filings are evaluated untouched.

Never edit a reviewed expected file to make a test pass; never review holdout rows while tuning templates.

Note: `golden/annotations/*.candidates.csv` are engine-generated candidates (not reviewed labels); they are kept on disk,
excluded from Git, and regenerated with `python -m bdc_soi annotate --actual <run dir> --golden golden --accession <acc>`.
