"""Authoritative company-by-period coverage matrix (52 filings): reconciliation, unresolved conflicts, approvals.

Usage: python scripts/coverage_matrix.py <universe run dir> <prior-run tag, e.g. s3d_final> [--out docs/coverage-matrix.md]
Writes docs/coverage-matrix.md and <universe run>/coverage_matrix.csv. Four things are kept separate per row:
(1) reconciliation within tolerance (engine self-consistency, full output); (2) unresolved extraction/source conflicts
(unmatched rows, ambiguous groups, unit mismatches, field conflicts); (3) implementation assumptions awaiting human
approval (excluded candidates and interpretation rules listed in docs/decision-pack.md); (4) independently assessed
accuracy, which is NOT ASSESSED for every row until reviewed golden data exists.
"""
from __future__ import annotations

import glob
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
# Interpretation items awaiting approval, keyed by cik (see docs/decision-pack.md).
PENDING_APPROVAL = {
    "1843162": "Q1 affiliate-schedule exclusion (CO Acquisition Vehicle LLC)",
    "1476765": "Q2 affiliate-schedule / parent-member exclusions",
    "1837532": "Q3 HTML '$' column as reporting currency",
    "1580345": "Q4 Nakdcom Hybrid: HTML-only holding vs excluded XBRL member",
    "1905824": "Q5 equal-valued groups without descriptions (sequence pairing)",
    "2020354": "Q5 equal-valued groups without descriptions (sequence pairing)",
    "1379785": "Q6 duplicate typed members / JV members in the affiliate schedule",
}


def _read_optional(path: Path, columns: list[str]) -> pd.DataFrame:
    """Runs without exclusions or matches write an empty (0-byte) file."""
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=columns)


def period_rows(run_dir: Path, period: str) -> list[dict]:
    h = pd.read_csv(run_dir / "holdings.csv", dtype=str, keep_default_na=False)
    v = pd.read_csv(run_dir / "validation.csv", dtype=str, keep_default_na=False)
    fd = pd.read_csv(run_dir / "filing_diagnostics.csv", dtype=str, keep_default_na=False)
    ex = _read_optional(run_dir / "excluded_candidates.csv", ["cik", "accession_number", "rule"])
    m = _read_optional(run_dir / "matching_diagnostics.csv", ["cik", "accession_number", "status"])
    rows = []
    for f in fd.itertuples():
        acc = f.accession_number
        hh = h[h.accession_number == acc]
        vv = v[v.accession_number == acc].set_index("field")
        rec = lambda fld, col: (vv.loc[fld, col] if fld in vv.index and col in vv.columns else "")
        flags = Counter(fl.split(":")[0] for s in hh.review_flags for fl in json.loads(s or "[]"))
        conflicts = int((hh.field_conflicts.map(lambda s: len(json.loads(s or "[]"))) > 0).sum())
        exc = ex[ex.accession_number == acc] if "accession_number" in ex.columns else ex.iloc[0:0]
        mm = m[m.accession_number == acc] if "accession_number" in m.columns else m.iloc[0:0]
        # Identity/sum-level conflicts decide the company status; field-level disagreements are listed separately.
        unresolved = {k: v_ for k, v_ in flags.items() if k in {"unmatched_html_row", "ambiguous_html_match", "xbrl_fair_value_unit_mismatch", "matched_by_sequence_tiebreak"}}
        field_level = {k: v_ for k, v_ in flags.items() if k in {"composite_conflict", "xbrl_html_conflict", "spread_out_of_bounds", "composite_no_match"}}
        rows.append({
            "cik": f.cik, "company": f.company_name, "period": period, "accession": acc, "report_date": f.report_date, "run": run_dir.name, "filing_status": f.status,
            "holdings": len(hh), "hybrid": int((hh.source_method == "hybrid_xbrl_html").sum()), "xbrl_only": int((hh.source_method == "xbrl").sum()), "html_only": int((hh.source_method == "html_only").sum()),
            "fv_status": rec("fair_value", "status"), "fv_complete_status": rec("fair_value", "complete_status"), "fv_reported_total": rec("fair_value", "reported_total"), "fv_difference": rec("fair_value", "difference"), "fv_tolerance": rec("fair_value", "tolerance"),
            "fv_in_scope_sum": rec("fair_value", "in_scope_sum"), "fv_complete_sum": rec("fair_value", "complete_exported_sum"), "scope_rows": rec("fair_value", "scope_rules"), "scope_rows_all": rec("fair_value", "scope_rows_all"),
            "duplicate_candidates": rec("fair_value", "duplicate_candidate_count"), "acceptance": rec("fair_value", "acceptance") or "not_assessed",
            "cost_status": rec("cost", "status"), "cost_complete_status": rec("cost", "complete_status"), "cost_difference": rec("cost", "difference"), "cost_tolerance": rec("cost", "tolerance"),
            "amortized_cost_status": rec("amortized_cost", "status") or "not_applicable",
            "ambiguous_matches": int((mm.status == "ambiguous").sum()) if len(mm) else 0,
            "unresolved_flags": json.dumps(dict(sorted(unresolved.items()))), "field_level_flags": json.dumps(dict(sorted(field_level.items()))), "rows_with_field_conflicts": conflicts,
            "excluded_candidates": json.dumps(dict(Counter(exc.rule))) if len(exc) else "{}",
            "pending_approval": PENDING_APPROVAL.get(f.cik, ""), "independent_accuracy": "NOT ASSESSED",
        })
    return rows


def main(argv: list[str]) -> None:
    import importlib.util
    spec = importlib.util.spec_from_file_location("coverage_report", ROOT / "scripts" / "coverage_report.py")
    cr = importlib.util.module_from_spec(spec); spec.loader.exec_module(cr)  # type: ignore[union-attr]
    prior_acc = cr.PRIOR_ACCESSIONS
    u = Path(argv[0]); tag = argv[1]
    out_md = Path(argv[argv.index("--out") + 1]) if "--out" in argv else ROOT / "docs" / "coverage-matrix.md"
    rows = period_rows(u, "latest")
    for d in sorted(glob.glob(str(ROOT / "output" / f"{tag}_*"))):
        acc = d.split("_")[-1]; cik = d.split("_")[-2]
        rows += period_rows(Path(d), "prior" if prior_acc.get(cik) == acc else "historical")
    df = pd.DataFrame(rows).sort_values(["company", "report_date"], ascending=[True, False]).reset_index(drop=True)
    hist = df[df.period == "historical"]
    df = df[df.period != "historical"].reset_index(drop=True)
    pd.concat([df, hist]).to_csv(u / "coverage_matrix.csv", index=False)
    # Company status is the worse of its periods: a latest-period pass never hides a prior-period failure.
    def recon_ok(r: pd.Series) -> bool:
        return r.fv_status == "pass" and r.cost_status in {"pass", "no_holdings", "not_tested"}
    comp = {}
    for cik, g in df.groupby("cik"):
        both = all(recon_ok(r) for _, r in g.iterrows())
        unresolved = any(json.loads(r.unresolved_flags) for _, r in g.iterrows())
        blocked = any(str(r.acceptance).startswith("blocked") for _, r in g.iterrows())
        comp[cik] = ("reconciled in both periods" if both else "reconciliation FAILS in >=1 period") + ("; ACCEPTANCE BLOCKED (unresolved identity contradiction)" if blocked else "") + ("; unresolved identity conflicts remain (unmatched/ambiguous/unit rows kept visible)" if unresolved else "; no unmatched or ambiguous rows") + ("; awaiting approval: " + PENDING_APPROVAL[cik] if cik in PENDING_APPROVAL else "")
    c = Counter(v.split(";")[0] for v in comp.values())
    lines = ["# Coverage matrix: 26 companies x 2 periods (52 filings) plus additional historical tests", "",
             f"Source runs: `{u.name}` (latest periods) and `output/{tag}_<cik>_<accession>` (prior periods); CSV: `{u.name}/coverage_matrix.csv`. Generated by `scripts/coverage_matrix.py`.", "",
             "Columns keep four things apart: **scoped reconciliation within tolerance** (fv/cost/amortized-cost status over the rows whose `reconciliation_scope` is in scope, next to the complete-exported status and both sums; rows scoped as cash equivalents after the grand total are legitimate positions kept in the output, D43; contradictory-identity duplicates are outside the sums by source evidence, D46; counts are published both for rows carrying a fair value and for all exported rows); **identity acceptance** (blocked whenever a contradictory-identity candidate is unresolved, regardless of tolerance); **unresolved extraction or source conflicts** (identity-level: unmatched rows, ambiguous groups, unit mismatches, sequence-paired rows; and field-level: recorded XBRL/HTML or composite disagreements; all rows stay in the output and are flagged); **implementation assumptions awaiting human approval** (excluded candidates and the decision-pack question that covers the company); **independently assessed accuracy** (NOT ASSESSED for every filing: no reviewed golden rows exist).", "",
             f"Company status (worse period wins): {dict(c)}.", "",
             "| Company | CIK | Period | Accession | Report date | Holdings (hybrid/xbrl-only/html-only) | FV scoped status | FV complete status | FV in-scope sum / complete sum | FV diff / tol | Cost scoped / complete | Cost diff / tol | Amort. cost | Rows with FV by scope | All exported rows by scope | Identity acceptance | Ambiguous | Unresolved identity flags | Field-level flags | Field-conflict rows | Excluded candidates | Awaiting approval | Accuracy |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for _, r in df.iterrows():
        lines.append(f"| {r.company} | {r.cik} | {r.period} | {r.accession} | {r.report_date} | {r.holdings} ({r.hybrid}/{r.xbrl_only}/{r.html_only}) | {r.fv_status} | {r.fv_complete_status} | {r.fv_in_scope_sum} / {r.fv_complete_sum} | {r.fv_difference} / {r.fv_tolerance} | {r.cost_status} / {r.cost_complete_status} | {r.cost_difference} / {r.cost_tolerance} | {r.amortized_cost_status} | {r.scope_rows} | {r.scope_rows_all} | {r.acceptance} | {r.ambiguous_matches} | {r.unresolved_flags} | {r.field_level_flags} | {r.rows_with_field_conflicts} | {r.excluded_candidates} | {r.pending_approval} | {r.independent_accuracy} |")
    if len(hist):
        lines += ["", "## Additional historical tests (not part of the 52-filing coverage count)", ""]
        for _, r in hist.iterrows():
            lines.append(f"- {r.company} ({r.cik}) {r.accession}, report date {r.report_date}: {r.holdings} holdings; fair value scoped {r.fv_status} / complete {r.fv_complete_status} (diff {r.fv_difference}, tol {r.fv_tolerance}); cost scoped {r.cost_status} / complete {r.cost_complete_status}; rows by scope {r.scope_rows}; run `{r.run}`")
    lines += ["", "## Company status (both periods)", ""] + [f"- {df[df.cik == cik].company.iloc[0]} ({cik}): {s}" for cik, s in sorted(comp.items(), key=lambda kv: df[df.cik == kv[0]].company.iloc[0])]
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", out_md, "and", u / "coverage_matrix.csv", dict(c))


if __name__ == "__main__":
    main(sys.argv[1:])
