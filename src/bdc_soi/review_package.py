"""Human-review package: Excel workbook export of candidate holdings and a validated import of reviewer decisions.

Nothing here marks a row as reviewed by itself: ``import_review`` only records rows where a reviewer filled in a
decision, a name and a date, and writes them to ``golden/expected`` with ``review_scope: sample`` manifests.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from bdc_soi.models import NORMALIZED_FIELDS
from bdc_soi.sec_client import accession_nodash

PROPOSED_FIELDS = ["issuer", "description", "industry", "investment_type", "reference_index", "spread", "spread_bps", "rate_floor", "interest_rate", "pik_rate", "maturity_date", "principal_amount", "shares", "cost", "amortized_cost", "fair_value", "currency", "affiliate_status"]
CORRECTABLE_FIELDS = ["issuer", "description", "industry", "reference_index", "spread_bps", "rate_floor", "maturity_date", "principal_amount", "shares", "cost", "fair_value", "currency", "reporting_currency"]
DECISIONS = {"approve", "correct", "reject", "unresolved"}  # unresolved: logged, never written to golden/expected
STRATA_ORDER = ["blocker:" , "ordinary_high_confidence", "repeated_issuer", "equity_like", "debt", "html_only", "xbrl_only", "hybrid"]


def stable_annotation_id(accession: str, holding_id: str) -> str:
    return f"{accession}-{holding_id[:12]}"


def sec_document_url(cik: str, accession: str, primary_document: str | None) -> str:
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash(accession)}"
    return f"{base}/{primary_document}" if primary_document else f"{base}/"


def _load_run(run_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    h = pd.read_csv(run_dir / "holdings.csv", dtype=str, keep_default_na=False)
    fd = pd.read_csv(run_dir / "filing_diagnostics.csv", dtype=str, keep_default_na=False)
    v = pd.read_csv(run_dir / "validation.csv", dtype=str, keep_default_na=False)
    hr = pd.read_csv(run_dir / "html_rows.csv", dtype=str, keep_default_na=False) if (run_dir / "html_rows.csv").exists() else pd.DataFrame()
    filings = pd.read_parquet(run_dir / "all_filings.parquet") if (run_dir / "all_filings.parquet").exists() else None
    return h, fd, v, hr, filings


def _is_equity_like(row: pd.Series) -> bool:
    text = f"{row.get('description', '')} {row.get('investment_type', '')}".lower()
    return (not row.get("maturity_date")) and bool(re.search(r"equity|stock|unit|share|warrant|preferred|common|membership|interest|lp\b", text))


@dataclass
class SampleRow:
    stratum: str
    holding: pd.Series


def stratified_sample(h: pd.DataFrame, per_company: int, seed: int) -> list[SampleRow]:
    """Deterministic stratified sample per (cik, accession): every distinct review-flag family and conflict type is
    represented (blocker categories), plus ordinary high-confidence rows, repeated issuers, equity-like and debt rows,
    and every extraction method. Within a stratum rows are chosen by seeded random order over holding_id."""
    out: list[SampleRow] = []
    for (cik, acc), g in h.groupby(["cik", "accession_number"], sort=True):
        g = g.sort_values("holding_id")
        rng = random.Random(f"{seed}:{cik}:{acc}")
        chosen: dict[str, str] = {}

        def take(stratum: str, cand: pd.DataFrame, n: int) -> None:
            ids = [i for i in cand.holding_id.tolist() if i not in chosen]
            rng.shuffle(ids)
            for i in ids[:n]:
                chosen[i] = stratum

        flags = g.review_flags.map(lambda s: [f.split(":")[0] for f in json.loads(s)])
        families = sorted({f for fl in flags for f in fl})
        for fam in families:
            take(f"blocker:{fam}", g[flags.map(lambda fl, fam=fam: fam in fl)], 2)
        conf_types = sorted({c["reason"] for fc in g.field_conflicts for c in json.loads(fc)})
        for ct in conf_types:
            take(f"blocker:conflict:{ct}", g[g.field_conflicts.map(lambda fc, ct=ct: any(c["reason"] == ct for c in json.loads(fc)))], 2)
        conf = pd.to_numeric(g.extraction_confidence, errors="coerce")
        ordinary = g[(flags.map(len) == 0) & (conf >= 0.7)]
        take("ordinary_high_confidence", ordinary, max(3, per_company // 3))
        counts = g.issuer.value_counts()
        rep = g[g.issuer.isin(counts[counts >= 2].index) & (g.issuer != "")]
        take("repeated_issuer", rep, 3)
        take("equity_like", g[g.apply(_is_equity_like, axis=1)], 2)
        take("debt", g[g.maturity_date != ""], 2)
        for m in ("html_only", "xbrl", "hybrid_xbrl_html"):
            take(f"method:{m}", g[g.source_method == m], 1)
        if len(chosen) < per_company:
            take("fill_random", g, per_company - len(chosen))
        for hid, stratum in chosen.items():
            out.append(SampleRow(stratum, g[g.holding_id == hid].iloc[0]))
    return out


IDENTITY_FLAGS = ("unmatched_html_row", "ambiguous_html_match", "xbrl_fair_value_unit_mismatch", "matched_by_sequence_tiebreak", "contradictory_identity_candidate", "group_level_identity", "canonical_candidate_by_source_evidence")


def triage_sample(h: pd.DataFrame, seed: int, per_period: int = 2, blocker_budget: int = 40) -> list[SampleRow]:
    """Small first batch: ``per_period`` ordinary rows for every (cik, accession) (one high-confidence row, then one
    repeated-issuer / equity-like / debt row in rotation), plus representative blockers drawn round-robin across
    companies, one per distinct (company, flag family) up to ``blocker_budget`` rows. Deterministic (seeded)."""
    out: list[SampleRow] = []
    chosen: set[str] = set()
    blocker_pool: dict[str, list[tuple[str, pd.Series]]] = {}
    for (cik, acc), g in h.groupby(["cik", "accession_number"], sort=True):
        g = g.sort_values("holding_id")
        rng = random.Random(f"{seed}:triage:{cik}:{acc}")
        flags = g.review_flags.map(lambda s: [f.split(":")[0] for f in json.loads(s or "[]")])
        conf = pd.to_numeric(g.extraction_confidence, errors="coerce")

        def pick(stratum: str, cand: pd.DataFrame) -> bool:
            ids = [i for i in cand.holding_id.tolist() if i not in chosen]
            if not ids:
                return False
            rng.shuffle(ids)
            chosen.add(ids[0])
            out.append(SampleRow(stratum, g[g.holding_id == ids[0]].iloc[0]))
            return True

        pick("ordinary_high_confidence", g[(flags.map(len) == 0) & (conf >= 0.7)]) or pick("ordinary_any", g[flags.map(len) == 0]) or pick("ordinary_any", g)
        counts = g.issuer.value_counts()
        rotation = [("repeated_issuer", g[g.issuer.isin(counts[counts >= 2].index) & (g.issuer != "")]), ("equity_like", g[g.apply(_is_equity_like, axis=1)]), ("debt", g[g.maturity_date != ""])]
        taken = 1
        for i in range(len(rotation)):
            if taken >= per_period:
                break
            name, cand = rotation[(hash(acc) + i) % len(rotation)]
            if pick(name, cand):
                taken += 1
        for fam in sorted({f for fl in flags for f in fl if f in IDENTITY_FLAGS or f.startswith("xbrl_html_conflict") or f.startswith("composite_conflict")}):
            cand = g[flags.map(lambda fl, fam=fam: fam in fl)]
            ids = [i for i in cand.holding_id.tolist() if i not in chosen]
            rng.shuffle(ids)
            if ids:
                blocker_pool.setdefault(f"{cik}:{fam}", []).append((f"blocker:{fam}", g[g.holding_id == ids[0]].iloc[0]))
    # Round-robin over (company, family) keys so every company with blockers is represented before any repeats.
    keys = sorted(blocker_pool)
    budget = blocker_budget
    by_company: dict[str, list[str]] = {}
    for k in keys:
        by_company.setdefault(k.split(":")[0], []).append(k)
    while budget > 0 and any(by_company.values()):
        for cik in sorted(by_company):
            if budget <= 0 or not by_company[cik]:
                continue
            k = by_company[cik].pop(0)
            stratum, row = blocker_pool[k][0]
            if row.holding_id not in chosen:
                chosen.add(row.holding_id)
                out.append(SampleRow(stratum, row))
                budget -= 1
    return out


DECISION_CASES = {
    "Q3_reporting_currency": lambda h: h.review_flags.str.contains("xbrl_fair_value_unit_mismatch"),
    "Q4_Q6_affiliate_schedule_html_only": lambda h: (h.source_method == "html_only") & h.issuer.str.contains("Nakdcom|Jocassee|Thompson Rivers|Waccamaw|Sierra Senior Loan", regex=True),
    "Q5_equal_valued_group_ambiguous": lambda h: h.review_flags.str.contains("ambiguous_html_match") & h.cik.isin(["1905824", "2020354"]),
    "Q6_duplicate_member_fv_only": lambda h: (h.source_method == "xbrl") & (h.cik == "1379785") & h.issuer.str.contains("Security Holdings"),
    "group_level_identity": lambda h: h.review_flags.str.contains("group_level_identity"),
    "contradictory_identity": lambda h: h.review_flags.str.contains("contradictory_identity_candidate"),
    "scope_cash_equivalent_after_total": lambda h: h.get("reconciliation_scope", pd.Series("", index=h.index)) == "cash_equivalent_after_total",
    "scope_after_total_section_in_scope": lambda h: h.get("reconciliation_scope", pd.Series("", index=h.index)) == "after_total_section",
}


def decision_case_sample(h: pd.DataFrame, seed: int, per_case: int = 3, chosen: set[str] | None = None) -> list[SampleRow]:
    """Representative rows for every open decision in docs/decision-pack.md and every new rule (scope, identity),
    ``per_case`` per (case, company) in seeded order; excluded XBRL candidates (Q1/Q2) live on their own sheet."""
    out: list[SampleRow] = []
    chosen = chosen if chosen is not None else set()
    for case, pred in DECISION_CASES.items():
        try:
            cand = h[pred(h)]
        except Exception:
            continue
        for cik, g in cand.groupby("cik"):
            ids = [i for i in sorted(g.holding_id) if i not in chosen]
            rng = random.Random(f"{seed}:{case}:{cik}")
            rng.shuffle(ids)
            for i in ids[:per_case]:
                chosen.add(i)
                out.append(SampleRow(f"decision:{case}", g[g.holding_id == i].iloc[0]))
    return out


def excluded_candidate_sheet(run_dirs: list[Path]) -> pd.DataFrame:
    """Every excluded XBRL candidate with evidence (Q1/Q2 decisions) and blank reviewer columns: a reviewer may
    'approve' the exclusion, 'reject' it (the member is a holding) or leave it 'unresolved'; never a golden label."""
    frames = []
    for run_dir in run_dirs:
        path = run_dir / "excluded_candidates.csv"
        if not path.exists():
            continue
        try:
            ex = pd.read_csv(path, dtype=str, keep_default_na=False)
        except pd.errors.EmptyDataError:
            continue
        ex["run"] = run_dir.name
        frames.append(ex)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    for col in ("reviewer_decision", "reviewer_name", "review_date", "reviewer_comment"):
        df[col] = ""
    return df


def blocker_inventory(run_dirs: list[Path]) -> pd.DataFrame:
    """Every row carrying an identity-level flag or a field conflict, across all runs (not sampled)."""
    frames = []
    for run_dir in run_dirs:
        h = pd.read_csv(run_dir / "holdings.csv", dtype=str, keep_default_na=False)
        flags = h.review_flags.map(lambda s: [f.split(":")[0] for f in json.loads(s or "[]")])
        has_conf = h.field_conflicts.map(lambda s: len(json.loads(s or "[]")) > 0)
        sel = h[flags.map(lambda fl: any(f in IDENTITY_FLAGS for f in fl)) | has_conf].copy()
        sel["run"] = run_dir.name
        sel["annotation_id"] = [stable_annotation_id(a, i) for a, i in zip(sel.accession_number, sel.holding_id)]
        sel["identity_flags"] = flags[sel.index].map(lambda fl: ";".join(sorted({f for f in fl if f in IDENTITY_FLAGS})))
        frames.append(sel[["annotation_id", "holding_id", "cik", "company_name", "accession_number", "report_date", "run", "source_method", "issuer", "description", "fair_value", "cost", "principal_amount", "shares", "currency", "reporting_currency", "source_table", "identity_flags", "review_flags", "field_conflicts", "extraction_confidence"]])
    return pd.concat(frames, ignore_index=True).sort_values(["cik", "accession_number", "holding_id"]).reset_index(drop=True) if frames else pd.DataFrame()


def build_review_workbook(run_dirs: list[Path], out_path: Path, per_company: int = 12, seed: int = 20261006, labels: dict[str, str] | None = None, profile: str = "full", blocker_budget: int = 40) -> dict[str, Any]:
    summary_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    loaded = [(run_dir, *_load_run(run_dir)) for run_dir in run_dirs]
    prim: dict[str, str] = {}
    html_by_id: dict[tuple[str, str], Any] = {}
    for run_dir, h, fd, v, hr, filings in loaded:
        if filings is not None and len(filings):
            prim.update(dict(zip(filings.accession_number.astype(str), filings.primary_document.astype(str))))
        if len(hr):
            html_by_id.update({(r.accession_number, r.row_id): r for r in hr.itertuples()})
    all_h = pd.concat([h for _, h, *_ in loaded], ignore_index=True)
    if profile == "triage":
        # One global sample so the blocker budget applies to the whole batch, not to every run directory; every open
        # decision and new rule is represented by decision-case rows on top of the ordinary rows and blockers.
        base_rows = triage_sample(all_h, seed, per_period=max(1, per_company), blocker_budget=blocker_budget)
        taken = {r.holding.holding_id for r in base_rows}
        samples: dict[str, list[SampleRow]] = {"*": base_rows + decision_case_sample(all_h, seed, per_case=2, chosen=taken)}
    else:
        samples = {run_dir.name: stratified_sample(h, per_company, seed) for run_dir, h, *_ in loaded}
    for run_dir, h, fd, v, hr, filings in loaded:
        for f in fd.itertuples():
            vv = v[v.accession_number == f.accession_number].set_index("field")
            rec = lambda fld, col: (vv.loc[fld, col] if fld in vv.index and col in vv.columns else "")
            summary_rows.append({
                "cik": f.cik, "company": f.company_name, "accession": f.accession_number, "report_date": f.report_date, "run": run_dir.name, "template": f.template_id,
                "holdings": f.holdings_count, "xbrl_status": f.xbrl_status, "html_status": f.html_status, "matched_rows": f.matched_rows, "unmatched_html_rows": f.unmatched_html_rows,
                "fair_value_status": rec("fair_value", "status"), "fair_value_complete_exported_sum": rec("fair_value", "complete_exported_sum"), "fair_value_in_scope_sum": rec("fair_value", "in_scope_sum"),
                "fair_value_reported_total": rec("fair_value", "reported_total"), "fair_value_source": rec("fair_value", "selected_source"), "fair_value_matched_only_diagnostic": rec("fair_value", "matched_only_status"),
                "fair_value_complete_status": rec("fair_value", "complete_status"), "fair_value_complete_exported_sum_note": "complete = every exported holding; in-scope = rows whose reconciliation_scope is schedule/after_total_section",
                "rows_by_reconciliation_scope": rec("fair_value", "scope_rules"),
                "cost_status": rec("cost", "status"), "cost_complete_status": rec("cost", "complete_status"), "cost_reported_total": rec("cost", "reported_total"), "amortized_cost_status": rec("amortized_cost", "status"),
                "notes": f.notes[:300], "sec_url": sec_document_url(f.cik, f.accession_number, prim.get(f.accession_number)),
            })
    for s in [x for lst in samples.values() for x in lst]:
        if True:
            r = s.holding
            lineage = json.loads(r.field_lineage or "{}")
            conflicts = json.loads(r.field_conflicts or "[]")
            html_row = html_by_id.get((r.accession_number, r.html_row_id)) if r.html_row_id else None
            row: dict[str, Any] = {
                "annotation_id": stable_annotation_id(r.accession_number, r.holding_id), "holding_id": r.holding_id, "cik": r.cik, "company": r.company_name, "accession": r.accession_number, "report_date": r.report_date,
                "sample_stratum": s.stratum, "source_method": r.source_method, "extraction_confidence": r.extraction_confidence,
            }
            for fld in PROPOSED_FIELDS:
                row[f"proposed_{fld}"] = r.get(fld, "")
            row["issuer_name_raw"] = r.issuer_name_raw
            row["description_raw"] = r.description_raw
            row["html_row_text"] = html_row.row_text if html_row is not None else ""
            row["reporting_currency_selected"] = r.reporting_currency
            row["xbrl_fair_value_unit_original"] = r.get("fair_value_unit_original", "") or next((a.get("value") for c in conflicts if c.get("field") == "reporting_currency" for a in c.get("alternatives", []) if a.get("source") == "xbrl_fact_unit"), "")
            row["principal_currency"] = r.currency
            row["reconciliation_scope"] = r.get("reconciliation_scope", "")
            row["scope_rule"] = r.get("scope_rule", "")
            row["scope_evidence"] = r.get("scope_evidence", "")
            row["identity_resolution"] = r.get("identity_resolution", "")
            row["match_group_id"] = r.get("match_group_id", "")
            row["conflict_classes"] = r.get("conflict_classes", "")
            row["sec_document_url"] = sec_document_url(r.cik, r.accession_number, prim.get(r.accession_number))
            row["source_table_row"] = r.source_table
            row["xbrl_member_key"] = r.holding_member_key
            row["xbrl_context_ids"] = r.source_context_ids
            row["xbrl_fact_ids"] = r.source_fact_ids
            row["lineage_summary"] = "; ".join(f"{k}={v.get('source')}" + (f"[{v.get('rule_id')}]" if v.get("rule_id") else "") for k, v in sorted(lineage.items()))
            row["field_conflicts"] = json.dumps(conflicts)[:1500]
            row["review_flags"] = r.review_flags
            row["reviewer_decision"] = ""
            for fld in CORRECTABLE_FIELDS:
                row[f"corrected_{fld}"] = ""
            row["reviewer_name"] = ""
            row["review_date"] = ""
            row["reviewer_comment"] = ""
            review_rows.append(row)
    instructions = [
        "Purpose: first human-review batch of candidate holdings. This batch alone does NOT establish the production thresholds (SPEC 19.6); acceptance stays NOT ASSESSED until enough reviewed rows exist per company.",
        ("Sampling method (triage profile): per company and period, " + str(max(1, per_company)) + " ordinary rows (one high-confidence row without flags, then one repeated-issuer / equity-like / debt row in rotation) plus representative blockers: one row per distinct (company, flag family) drawn round-robin across companies up to a budget of " + str(blocker_budget) + " rows; seeded, deterministic. The complete blocker inventory is a separate CSV. This batch is a triage and annotation set, not sufficient evidence for production acceptance." if profile == "triage" else "Sampling method: per company and period, deterministic stratified sample (seed in the Summary sheet): up to 2 rows for every review-flag family and every field-conflict type ('blocker:*' strata), ordinary high-confidence rows (no flags, confidence >= 0.70), repeated issuers (issuers with >= 2 facilities, to check facility identity), equity-like and debt rows, and one row per extraction method (hybrid, XBRL-only, HTML-only). Within a stratum rows are drawn in seeded random order of holding_id."),
        "Reconciliation columns on the summary sheet are SCOPED: fair_value_status compares the rows whose reconciliation_scope is in scope with the reported total; fair_value_complete_status compares every exported row. Rows scoped cash_equivalent_after_total (money-market / treasury positions printed after the grand total) or subsidiary_context are legitimate positions kept in the batch; their scope_rule and scope_evidence columns show why they sit outside the schedule total.",
        "Currency columns: reporting_currency_selected is the engine's reporting currency for the fair value (rule D33 where it differs); xbrl_fair_value_unit_original is the unit tagged on the XBRL fact; principal_currency is the par/principal currency. Use corrected_reporting_currency to overrule the selection.",
        "identity_resolution = group means the row belongs to a group of equal-valued rows that could only be paired at group level (match_group_id); the HTML fields were kept only where every row of the group agrees. conflict_classes counts recorded disagreements by class: formatting (punctuation/legal suffix/containment), identity (issuer/description substance), semantic (vocabulary fields), numeric.",
        "Reviewer decisions: approve, correct (fill corrected_* columns), reject (not a holding of this schedule) or unresolved (the identity or scope cannot be decided from the filing; add the open question in reviewer_comment). 'unresolved' is logged under golden/review_log and never becomes an approved golden label. The excluded_candidates sheet lists XBRL members kept out of the canonical output (decisions Q1/Q2): approve = the exclusion is right, reject = the member is a holding, unresolved = open.",
        "How to review a row: open sec_document_url, locate the row using source_table_row (HTML table/row ids) or xbrl_member_key / xbrl_context_ids (XBRL), compare the proposed_* values with the filing. Fill reviewer_decision with approve, correct or reject (reject = the row is not a holding of this schedule). For 'correct', put the right value(s) in the corrected_* columns (ISO dates, decimal rates e.g. 0.045, spread_bps in basis points, monetary values in whole filing-currency units). Always fill reviewer_name and review_date (YYYY-MM-DD); rows without all three are ignored by the import.",
        "Units: proposed_spread is a decimal rate, proposed_spread_bps basis points; monetary fields are in whole currency units; xbrl_fair_value_unit is the unit tagged on the fair-value fact (may differ from the schedule currency; see field_conflicts for reporting_currency evidence).",
        "Import: python -m bdc_soi import-review --workbook <this file> --golden golden  -> writes golden/expected/<accession>.csv for reviewed rows only and sets the manifest to review_status: reviewed, review_scope: sample. Development/regression/holdout splits in the manifests are preserved; never review holdout rows while tuning templates.",
        "Do not edit proposed_* columns; corrections go in corrected_* columns. Leave rows you did not review blank.",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        pd.DataFrame({"instructions": instructions}).to_excel(w, sheet_name="instructions", index=False)
        pd.DataFrame(summary_rows).to_excel(w, sheet_name="summary", index=False)
        pd.DataFrame(review_rows).to_excel(w, sheet_name="review_batch", index=False)
        pd.DataFrame([{"seed": seed, "per_company": per_company, "runs": ";".join(str(r) for r in run_dirs), "generated": "see run manifests"}]).to_excel(w, sheet_name="sampling", index=False)
        exc = excluded_candidate_sheet(run_dirs)
        if len(exc):
            exc.to_excel(w, sheet_name="excluded_candidates", index=False)
        for ws in w.book.worksheets:
            ws.freeze_panes = "A2"
    strata = pd.Series([r["sample_stratum"].split(":")[0] for r in review_rows]).value_counts().to_dict() if review_rows else {}
    return {"path": str(out_path), "summary_rows": len(summary_rows), "review_rows": len(review_rows), "strata": strata}


def import_review(workbook: Path, golden_dir: Path, today: date | None = None) -> dict[str, Any]:
    """Validate reviewer entries and write reviewed rows to golden/expected. Rows without decision+name+date are skipped."""
    df = pd.read_excel(workbook, sheet_name="review_batch", dtype=str).fillna("")
    today = today or date.today()
    problems: list[str] = []
    accepted: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for i, r in df.iterrows():
        decision = str(r.get("reviewer_decision", "")).strip().lower()
        name = str(r.get("reviewer_name", "")).strip()
        rdate = str(r.get("review_date", "")).strip()[:10]
        if not decision and not name and not rdate:
            continue
        if decision not in DECISIONS:
            problems.append(f"row {i + 2} ({r['annotation_id']}): reviewer_decision must be approve/correct/reject/unresolved, got {decision!r}")
            continue
        if not name or not rdate:
            problems.append(f"row {i + 2} ({r['annotation_id']}): reviewer_name and review_date are required")
            continue
        try:
            d = date.fromisoformat(rdate)
        except ValueError:
            problems.append(f"row {i + 2} ({r['annotation_id']}): review_date must be YYYY-MM-DD")
            continue
        if d > today:
            problems.append(f"row {i + 2} ({r['annotation_id']}): review_date is in the future")
            continue
        rec: dict[str, Any] = {"annotation_id": r["annotation_id"], "holding_id": r["holding_id"], "cik": r["cik"], "accession_number": r["accession"], "report_date": r["report_date"], "source_table": r.get("source_table_row", ""), "source_context": r.get("xbrl_member_key", ""), "decision": decision, "reviewer": name, "review_date": rdate, "comments": r.get("reviewer_comment", "")}
        for fld in NORMALIZED_FIELDS:
            val = r.get(f"proposed_{fld}", "")
            if fld in ("issuer_name_raw", "description_raw"):
                val = r.get(fld, "")
            if decision == "correct" and fld in CORRECTABLE_FIELDS and str(r.get(f"corrected_{fld}", "")).strip() != "":
                val = str(r.get(f"corrected_{fld}")).strip()
            rec[fld] = "" if decision == "reject" else val
        if decision == "correct" and not any(str(r.get(f"corrected_{f}", "")).strip() for f in CORRECTABLE_FIELDS):
            problems.append(f"row {i + 2} ({r['annotation_id']}): decision 'correct' needs at least one corrected_* value")
            continue
        if decision == "unresolved":
            if not str(r.get("reviewer_comment", "")).strip():
                problems.append(f"row {i + 2} ({r['annotation_id']}): decision 'unresolved' needs a reviewer_comment stating the open question")
                continue
            unresolved.append(rec)  # recorded in golden/review_log, never an approved golden label
            continue
        accepted.append(rec)
    if problems:
        return {"written": {}, "problems": problems, "accepted_rows": 0, "unresolved_rows": 0}
    if unresolved:
        log_dir = Path(golden_dir) / "review_log"
        log_dir.mkdir(parents=True, exist_ok=True)
        for acc, rows in pd.DataFrame(unresolved).groupby("accession_number"):
            path = log_dir / f"{acc}.unresolved.csv"
            existing = pd.read_csv(path, dtype=str, keep_default_na=False) if path.exists() else pd.DataFrame()
            merged = pd.concat([existing[~existing.annotation_id.isin(rows.annotation_id)] if len(existing) else existing, rows], ignore_index=True)
            merged.sort_values("annotation_id").to_csv(path, index=False, lineterminator="\n")
    written: dict[str, int] = {}
    exp_dir = Path(golden_dir) / "expected"
    exp_dir.mkdir(parents=True, exist_ok=True)
    for acc, rows in pd.DataFrame(accepted).groupby("accession_number") if accepted else []:
        path = exp_dir / f"{acc}.csv"
        existing = pd.read_csv(path, dtype=str, keep_default_na=False) if path.exists() else pd.DataFrame()
        merged = pd.concat([existing[~existing.annotation_id.isin(rows.annotation_id)] if len(existing) else existing, rows], ignore_index=True)
        merged.sort_values("annotation_id").to_csv(path, index=False, lineterminator="\n")
        written[acc] = len(merged)
        mpath = Path(golden_dir) / "manifests" / f"{acc}.yml"
        manifest = yaml.safe_load(mpath.read_text()) if mpath.exists() else {"cik": rows.cik.iloc[0], "accession_number": acc, "split": "development"}
        manifest.update({"review_status": "reviewed", "review_scope": "sample", "reviewed_rows": int(len(merged)), "reviewer": ";".join(sorted(set(merged.reviewer))), "review_date": str(max(merged.review_date)), "expected_file": f"{acc}.csv"})
        mpath.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True))
    return {"written": written, "problems": [], "accepted_rows": len(accepted), "unresolved_rows": len(unresolved)}
