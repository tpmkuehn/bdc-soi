"""Golden-dataset evaluation: manifests, weighted bipartite alignment, metrics, thresholds (SPEC 19).

Golden layout::

    golden/manifests/<accession>.yml   -> cik, accession, split, review_status, reviewer, review_date, expected file
    golden/expected/<accession>.csv    -> reviewed canonical rows (annotation_id, fields..., reviewer, review_date, comments)
    golden/annotations/<accession>.candidates.csv -> unreviewed candidates generated from a run

Only manifests with ``review_status: reviewed`` count toward acceptance. Unreviewed candidates may be
evaluated for engineering feedback but are reported as NOT ASSESSED for acceptance.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from bdc_soi.models import NORMALIZED_FIELDS
from bdc_soi.normalization import text_key

ACCEPTANCE_THRESHOLDS = {
    "row_precision": 0.98,
    "row_recall": 0.97,
    "fair_value_accuracy": 0.99,
    "cost_accuracy": 0.98,
    "issuer_normalized_accuracy": 0.97,
    "description_normalized_accuracy": 0.95,
    "maturity_date_accuracy": 0.98,
    "fair_value_reconciliation_rate": 0.95,
    "duplicate_row_rate_max": 0.005,
    "unexplained_runtime_failures_max": 0,
}
MONETARY = {"principal_amount", "face_amount", "cost", "amortized_cost", "fair_value", "shares"}
PERCENT = {"spread", "cash_rate", "pik_rate", "rate_floor", "interest_rate", "percent_of_net_assets"}
TEXT = {"issuer", "description", "industry", "sector", "country", "investment_type", "reference_index", "currency", "affiliate_status", "controlled_status"}
ALIGN_WEIGHTS = {"issuer": 3.0, "description": 2.0, "maturity_date": 1.5, "principal_amount": 1.5, "cost": 1.5, "fair_value": 2.0, "source_identity": 4.0}


@dataclass
class GoldenManifest:
    path: Path
    cik: str
    accession_number: str
    split: str
    review_status: str
    reviewer: str | None
    review_date: str | None
    expected_file: Path | None
    report_date: str | None = None
    notes: str | None = None
    review_scope: str = "full"  # full | sample (expected file covers only the listed holding_ids)


def load_manifests(golden_dir: Path) -> list[GoldenManifest]:
    out: list[GoldenManifest] = []
    mdir = Path(golden_dir) / "manifests"
    for p in sorted(mdir.glob("*.yml")) + sorted(mdir.glob("*.yaml")):
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        exp = data.get("expected_file")
        exp_path = None
        if exp:
            # normpath resolves ".." lexically even when the expected/ directory does not exist.
            candidates = [Path(os.path.normpath(Path(golden_dir) / "expected" / exp)), Path(os.path.normpath(Path(golden_dir) / exp)), Path(exp)]
            exp_path = next((c for c in candidates if c.exists()), candidates[0])
        out.append(
            GoldenManifest(
                path=p,
                cik=str(data.get("cik", "")).lstrip("0"),
                accession_number=str(data.get("accession_number", "")),
                split=str(data.get("split", "development")),
                review_status=str(data.get("review_status", "unreviewed")),
                reviewer=data.get("reviewer"),
                review_date=str(data.get("review_date")) if data.get("review_date") else None,
                expected_file=exp_path,
                report_date=str(data.get("report_date")) if data.get("report_date") else None,
                notes=data.get("notes"),
                review_scope=str(data.get("review_scope", "full")),
            )
        )
    return out


def _is_null(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    return False


def _num(v: Any) -> float | None:
    if _is_null(v):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def values_match(fld: str, a: Any, b: Any) -> tuple[bool, str]:
    """Return (match, mode) using SPEC 19.5 tolerances."""
    if _is_null(a) and _is_null(b):
        return True, "null"
    if _is_null(a) or _is_null(b):
        return False, "null_mismatch"
    if fld in MONETARY:
        fa, fb = _num(a), _num(b)
        if fa is None or fb is None:
            return False, "numeric_parse"
        return abs(fa - fb) <= max(1.0, abs(fb) * 1e-4), "numeric"
    if fld in PERCENT:
        fa, fb = _num(a), _num(b)
        if fa is None or fb is None:
            return str(a) == str(b), "text"
        return abs(fa - fb) <= 0.0001, "numeric"
    if fld == "spread_bps":
        fa, fb = _num(a), _num(b)
        if fa is None or fb is None:
            return False, "numeric_parse"
        return abs(fa - fb) <= 0.5, "numeric"
    if fld in {"issue_date", "maturity_date"}:
        return str(a)[:10] == str(b)[:10], "date"
    if fld == "non_accrual_flag":
        return str(a).lower() == str(b).lower(), "bool"
    return text_key(str(a)) == text_key(str(b)), "normalized_text"


def pair_score(actual: dict[str, Any], expected: dict[str, Any]) -> float:
    s = 0.0
    for fld, w in ALIGN_WEIGHTS.items():
        if fld == "source_identity":
            a_id = actual.get("holding_member_key") or actual.get("source_table")
            e_id = expected.get("source_context") or expected.get("source_table")
            if not _is_null(a_id) and not _is_null(e_id) and str(a_id) == str(e_id):
                s += w
            continue
        ok, _ = values_match(fld, actual.get(fld), expected.get(fld))
        if ok and not (_is_null(actual.get(fld)) and _is_null(expected.get(fld))):
            s += w
    return s


def hungarian(cost: list[list[float]]) -> list[int]:
    """Minimum-cost assignment (rows -> columns) for a rectangular matrix with n <= m."""
    n = len(cost)
    m = len(cost[0]) if cost else 0
    if n == 0 or m == 0:
        return []
    INF = float("inf")
    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    p = [0] * (m + 1)
    way = [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [INF] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = INF
            j1 = 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    assignment = [-1] * n
    for j in range(1, m + 1):
        if p[j] != 0:
            assignment[p[j] - 1] = j - 1
    return assignment


def align_rows(actual: list[dict[str, Any]], expected: list[dict[str, Any]], min_score: float = 3.0, margin: float = 1.0) -> list[dict[str, Any]]:
    """Weighted bipartite alignment with ambiguity reporting (19.3)."""
    pairs: dict[tuple[int, int], float] = {}
    for i, a in enumerate(actual):
        for j, e in enumerate(expected):
            s = pair_score(a, e)
            if s >= min_score:
                pairs[(i, j)] = s
    # Connected components of the candidate graph keep the Hungarian matrices small.
    adj: dict[int, set[int]] = {}
    for (i, j) in pairs:
        adj.setdefault(("a", i), set()).add(("e", j))  # type: ignore[arg-type]
        adj.setdefault(("e", j), set()).add(("a", i))  # type: ignore[arg-type]
    seen: set = set()
    results: list[dict[str, Any]] = []
    matched_a: set[int] = set()
    matched_e: set[int] = set()
    for node in sorted(adj):
        if node in seen:
            continue
        comp: list = []
        stack = [node]
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            comp.append(n)
            stack.extend(adj.get(n, ()))
        a_idx = sorted(x[1] for x in comp if x[0] == "a")
        e_idx = sorted(x[1] for x in comp if x[0] == "e")
        big = 1000.0
        transpose = len(a_idx) > len(e_idx)
        rows, cols = (e_idx, a_idx) if transpose else (a_idx, e_idx)
        matrix = [[big - pairs.get((c, r) if transpose else (r, c), 0.0) for c in cols] for r in rows]
        assignment = hungarian(matrix)
        for ri, ci in enumerate(assignment):
            if ci < 0:
                continue
            i, j = (cols[ci], rows[ri]) if transpose else (rows[ri], cols[ci])
            s = pairs.get((i, j), 0.0)
            if s < min_score:
                continue
            others_a = sorted((pairs[(i, jj)] for jj in e_idx if jj != j and (i, jj) in pairs), reverse=True)
            others_e = sorted((pairs[(ii, j)] for ii in a_idx if ii != i and (ii, j) in pairs), reverse=True)
            second = max(others_a[0] if others_a else 0.0, others_e[0] if others_e else 0.0)
            status = "aligned" if s - second >= margin else "ambiguous"
            results.append({"actual_index": i, "expected_index": j, "score": s, "second_score": second, "status": status})
            matched_a.add(i)
            matched_e.add(j)
    for i in range(len(actual)):
        if i not in matched_a:
            results.append({"actual_index": i, "expected_index": None, "score": 0.0, "second_score": None, "status": "unmatched_actual"})
    for j in range(len(expected)):
        if j not in matched_e:
            results.append({"actual_index": None, "expected_index": j, "score": 0.0, "second_score": None, "status": "unmatched_expected"})
    return results


@dataclass
class EvaluationReport:
    reviewed_filings: int
    unreviewed_filings: int
    row_metrics: dict[str, Any]
    field_metrics: dict[str, dict[str, Any]]
    filing_metrics: dict[str, Any]
    template_metrics: dict[str, Any]
    acceptance: dict[str, Any]
    per_filing: list[dict[str, Any]] = field(default_factory=list)
    alignments: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _safe_div(n: float, d: float) -> float | None:
    return None if d == 0 else round(n / d, 6)


def evaluate_run(actual_dir: Path, golden_dir: Path, report_dir: Path, *, splits: list[str] | None = None, include_unreviewed: bool = False) -> EvaluationReport:
    actual_dir, golden_dir, report_dir = Path(actual_dir), Path(golden_dir), Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    holdings = pd.read_csv(actual_dir / "holdings.csv", dtype=str, keep_default_na=False) if (actual_dir / "holdings.csv").exists() else pd.DataFrame()
    validation = pd.read_csv(actual_dir / "validation.csv", dtype=str, keep_default_na=False) if (actual_dir / "validation.csv").exists() else pd.DataFrame()
    diagnostics = pd.read_csv(actual_dir / "filing_diagnostics.csv", dtype=str, keep_default_na=False) if (actual_dir / "filing_diagnostics.csv").exists() else pd.DataFrame()
    usage = pd.read_csv(actual_dir / "template_usage.csv", dtype=str, keep_default_na=False) if (actual_dir / "template_usage.csv").exists() else pd.DataFrame()
    manifests = load_manifests(golden_dir)
    if splits:
        manifests = [m for m in manifests if m.split in splits]
    reviewed = [m for m in manifests if m.review_status == "reviewed" and m.expected_file and m.expected_file.exists()]
    unreviewed = [m for m in manifests if m.review_status != "reviewed"]
    use = reviewed + (unreviewed if include_unreviewed else [])
    notes: list[str] = []
    if not reviewed:
        notes.append("No reviewed golden filings: acceptance thresholds are NOT ASSESSED.")
    tp = fp = fn = 0
    dup_rows = spurious_total = 0
    field_counts: dict[str, dict[str, int]] = {f: {"tp_pop": 0, "fp_pop": 0, "fn_pop": 0, "exact": 0, "norm": 0, "num": 0, "num_total": 0, "null_ok": 0, "null_total": 0, "compared": 0} for f in NORMALIZED_FIELDS}
    per_filing: list[dict[str, Any]] = []
    alignments: list[dict[str, Any]] = []
    for m in use:
        exp_df = pd.read_csv(m.expected_file, dtype=str, keep_default_na=False) if m.expected_file and m.expected_file.exists() else pd.DataFrame()
        expected_all = [{k: (None if v == "" else v) for k, v in row.items()} for row in exp_df.to_dict("records")]
        rejected_ids = {e.get("holding_id") for e in expected_all if (e.get("decision") or "") == "reject"}
        expected = [e for e in expected_all if (e.get("decision") or "") != "reject"]
        act_df = holdings[(holdings.get("accession_number", pd.Series(dtype=str)) == m.accession_number)] if len(holdings) else pd.DataFrame()
        if m.review_scope == "sample" and len(act_df):
            scoped_ids = {e.get("holding_id") for e in expected_all if e.get("holding_id")}
            act_df = act_df[act_df.holding_id.isin(scoped_ids)]  # sample scope: only reviewed holding_ids are judged
            notes.append(f"{m.accession_number}: sample-scoped review ({len(scoped_ids)} rows); row metrics cover the sample only")
        actual = [{k: (None if v == "" else v) for k, v in row.items()} for row in act_df.to_dict("records")]
        if rejected_ids:
            notes.append(f"{m.accession_number}: {len(rejected_ids)} reviewer-rejected rows count as false positives when present")
        aligned = align_rows(actual, expected)
        f_tp = sum(1 for a in aligned if a["status"] in {"aligned", "ambiguous"})
        f_fp = sum(1 for a in aligned if a["status"] == "unmatched_actual")
        f_fn = sum(1 for a in aligned if a["status"] == "unmatched_expected")
        tp, fp, fn = tp + f_tp, fp + f_fp, fn + f_fn
        ids = [a.get("holding_id") for a in actual]
        dup_rows += len(ids) - len(set(ids))
        spurious_total += sum(1 for a in actual if str(a.get("issuer") or "").lower().startswith("total") or str(a.get("description") or "").lower().startswith("total"))
        for a in aligned:
            rec = {**a, "accession_number": m.accession_number, "split": m.split, "review_status": m.review_status}
            if a["actual_index"] is not None:
                rec["actual_holding_id"] = actual[a["actual_index"]].get("holding_id")
            if a["expected_index"] is not None:
                rec["annotation_id"] = expected[a["expected_index"]].get("annotation_id")
            alignments.append(rec)
            if a["status"] not in {"aligned", "ambiguous"}:
                continue
            arow, erow = actual[a["actual_index"]], expected[a["expected_index"]]
            for fld in NORMALIZED_FIELDS:
                if fld not in erow:
                    continue  # field not annotated for this golden file
                c = field_counts[fld]
                c["compared"] += 1
                av, ev = arow.get(fld), erow.get(fld)
                ok, mode = values_match(fld, av, ev)
                if _is_null(ev):
                    c["null_total"] += 1
                    if _is_null(av):
                        c["null_ok"] += 1
                    else:
                        c["fp_pop"] += 1
                else:
                    if _is_null(av):
                        c["fn_pop"] += 1
                    else:
                        c["tp_pop"] += 1
                        if ok:
                            c["norm"] += 1
                        if str(av).strip() == str(ev).strip():
                            c["exact"] += 1
                        if mode == "numeric":
                            c["num_total"] += 1
                            if ok:
                                c["num"] += 1
        per_filing.append({"accession_number": m.accession_number, "cik": m.cik, "split": m.split, "review_status": m.review_status, "expected_rows": len(expected), "actual_rows": len(actual), "tp": f_tp, "fp": f_fp, "fn": f_fn, "precision": _safe_div(f_tp, f_tp + f_fp), "recall": _safe_div(f_tp, f_tp + f_fn)})
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1 = None if precision is None or recall is None or (precision + recall) == 0 else round(2 * precision * recall / (precision + recall), 6)
    total_actual = sum(p["actual_rows"] for p in per_filing)
    row_metrics = {"tp": tp, "fp": fp, "fn": fn, "row_precision": precision, "row_recall": recall, "row_f1": f1, "duplicate_row_rate": _safe_div(dup_rows, total_actual), "spurious_total_row_rate": _safe_div(spurious_total, total_actual)}
    field_metrics: dict[str, dict[str, Any]] = {}
    for fld, c in field_counts.items():
        if c["compared"] == 0:
            continue
        field_metrics[fld] = {
            "compared": c["compared"],
            "populated_precision": _safe_div(c["tp_pop"], c["tp_pop"] + c["fp_pop"]),
            "populated_recall": _safe_div(c["tp_pop"], c["tp_pop"] + c["fn_pop"]),
            "exact_match_accuracy": _safe_div(c["exact"], c["tp_pop"]),
            "normalized_accuracy": _safe_div(c["norm"], c["tp_pop"]),
            "numeric_accuracy_within_tolerance": _safe_div(c["num"], c["num_total"]),
            "null_accuracy": _safe_div(c["null_ok"], c["null_total"]),
        }
    # Filing metrics from the run (all filings in the run, not only golden ones).
    fm: dict[str, Any] = {}
    if len(validation):
        for fld in ("fair_value", "cost", "amortized_cost"):
            sub = validation[validation["field"] == fld]
            tested = sub[~sub["status"].isin(["not_tested", "no_holdings"])]
            fm[f"{fld}_reconciliation_rate"] = _safe_div(int((tested["status"] == "pass").sum()), len(tested))
    if len(diagnostics):
        n = len(diagnostics)
        fm["filings"] = n
        fm["pct_filings_with_holdings"] = _safe_div(int((diagnostics["holdings_count"].astype(int) > 0).sum()), n)
        review_needed = 0
        unmatched_ratio = []
        conflict_ratio = []
        for _, d in diagnostics.iterrows():
            hc = int(d.get("holdings_count") or 0)
            if d.get("status") != "ok" or d.get("fair_value_reconciliation") in {"fail", "ambiguous_total", "review"}:
                review_needed += 1
            hr = int(d.get("html_rows") or 0)
            if hr:
                unmatched_ratio.append(int(d.get("unmatched_html_rows") or 0) / hr)
            if hc:
                conflict_ratio.append(int(d.get("conflicts") or 0) / hc)
        fm["pct_filings_requiring_review"] = _safe_div(review_needed, n)
        fm["unmatched_html_rate"] = round(sum(unmatched_ratio) / len(unmatched_ratio), 6) if unmatched_ratio else None
        fm["field_conflict_rate"] = round(sum(conflict_ratio) / len(conflict_ratio), 6) if conflict_ratio else None
        fm["unexplained_runtime_failures"] = int((diagnostics["status"] == "failed").sum())
    tm: dict[str, Any] = {}
    if len(usage):
        tm["filings_using_generic_template"] = int((usage["template_kind"] == "generic").sum())
        tm["filings_using_company_template"] = int((usage["template_kind"] == "company").sum())
        tm["unknown_format_count"] = int((usage["holdings"].astype(int) == 0).sum())
        tm["by_template_id"] = {k: int(v) for k, v in usage.groupby("template_id")["holdings"].count().items()}
    acceptance = _acceptance(row_metrics, field_metrics, fm, bool(reviewed))
    report = EvaluationReport(len(reviewed), len(unreviewed), row_metrics, field_metrics, fm, tm, acceptance, per_filing, alignments, notes)
    (report_dir / "evaluation_report.json").write_text(json.dumps(report.__dict__, indent=2, default=str), encoding="utf-8")
    pd.DataFrame(alignments).to_csv(report_dir / "alignment.csv", index=False, lineterminator="\n")
    pd.DataFrame(per_filing).to_csv(report_dir / "per_filing.csv", index=False, lineterminator="\n")
    rows = [{"metric": k, "value": v} for k, v in row_metrics.items()] + [{"metric": f"{f}.{k}", "value": v} for f, d in field_metrics.items() for k, v in d.items()] + [{"metric": k, "value": v} for k, v in fm.items()]
    pd.DataFrame(rows).to_csv(report_dir / "metrics.csv", index=False, lineterminator="\n")
    (report_dir / "summary.md").write_text(_summary_md(report), encoding="utf-8")
    return report


def _acceptance(row: dict[str, Any], fields: dict[str, dict[str, Any]], fm: dict[str, Any], reviewed: bool) -> dict[str, Any]:
    def status(value: float | None, threshold: float, higher_is_better: bool = True) -> str:
        if not reviewed or value is None:
            return "NOT ASSESSED"
        ok = value >= threshold if higher_is_better else value <= threshold
        return "PASS" if ok else "FAIL"

    def acc(fld: str) -> float | None:
        d = fields.get(fld)
        return d.get("normalized_accuracy") if d else None

    cost_vals = [v for v in (acc("cost"), acc("amortized_cost")) if v is not None]
    return {
        "reviewed_observations": reviewed,
        "holding_row_precision": {"value": row.get("row_precision"), "minimum": 0.98, "status": status(row.get("row_precision"), 0.98)},
        "holding_row_recall": {"value": row.get("row_recall"), "minimum": 0.97, "status": status(row.get("row_recall"), 0.97)},
        "fair_value_accuracy": {"value": acc("fair_value"), "minimum": 0.99, "status": status(acc("fair_value"), 0.99)},
        "cost_amortized_cost_accuracy": {"value": min(cost_vals) if cost_vals else None, "minimum": 0.98, "status": status(min(cost_vals) if cost_vals else None, 0.98)},
        "issuer_normalized_accuracy": {"value": acc("issuer"), "minimum": 0.97, "status": status(acc("issuer"), 0.97)},
        "description_normalized_accuracy": {"value": acc("description"), "minimum": 0.95, "status": status(acc("description"), 0.95)},
        "maturity_date_accuracy": {"value": acc("maturity_date"), "minimum": 0.98, "status": status(acc("maturity_date"), 0.98)},
        "fair_value_reconciliation_pass_rate": {"value": fm.get("fair_value_reconciliation_rate"), "minimum": 0.95, "status": status(fm.get("fair_value_reconciliation_rate"), 0.95)},
        "duplicate_row_rate": {"value": row.get("duplicate_row_rate"), "maximum": 0.005, "status": status(row.get("duplicate_row_rate"), 0.005, False)},
        "unexplained_runtime_failures": {"value": fm.get("unexplained_runtime_failures"), "maximum": 0, "status": status(fm.get("unexplained_runtime_failures"), 0, False)},
    }


def _summary_md(r: EvaluationReport) -> str:
    lines = ["# Evaluation summary", "", f"Reviewed golden filings: {r.reviewed_filings}; unreviewed candidates: {r.unreviewed_filings}", ""]
    for n in r.notes:
        lines.append(f"> {n}")
    lines += ["", "## Row metrics", ""] + [f"- {k}: {v}" for k, v in r.row_metrics.items()]
    lines += ["", "## Field metrics (normalized accuracy / populated recall)", ""] + [f"- {f}: norm={d['normalized_accuracy']} recall={d['populated_recall']} n={d['compared']}" for f, d in r.field_metrics.items()]
    lines += ["", "## Filing metrics", ""] + [f"- {k}: {v}" for k, v in r.filing_metrics.items()]
    lines += ["", "## Acceptance (SPEC 19.6)", ""] + [f"- {k}: {v['status']} (value={v['value']})" for k, v in r.acceptance.items() if isinstance(v, dict)]
    return "\n".join(lines) + "\n"


def write_candidate_annotations(actual_dir: Path, golden_dir: Path, accession: str) -> Path:
    """Export a run's holdings for an accession as UNREVIEWED annotation candidates."""
    holdings = pd.read_csv(Path(actual_dir) / "holdings.csv", dtype=str, keep_default_na=False)
    sub = holdings[holdings["accession_number"] == accession].copy()
    if sub.empty:
        raise ValueError(f"no holdings for accession {accession} in {actual_dir}")
    cols = ["holding_id", "cik", "accession_number", "report_date", "source_table", "holding_member_key"] + list(NORMALIZED_FIELDS)
    out = sub[cols].copy()
    out.insert(0, "annotation_id", [f"{accession}-{i:04d}" for i in range(1, len(out) + 1)])
    out = out.rename(columns={"holding_member_key": "source_context"})
    out["review_status"] = "unreviewed"
    out["reviewer"] = ""
    out["review_date"] = ""
    out["comments"] = ""
    ann_dir = Path(golden_dir) / "annotations"
    ann_dir.mkdir(parents=True, exist_ok=True)
    path = ann_dir / f"{accession}.candidates.csv"
    out.to_csv(path, index=False, lineterminator="\n")
    return path
