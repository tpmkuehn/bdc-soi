"""Review workbook export, validated import, and sample-scoped evaluation on the synthetic run."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import yaml

from bdc_soi.evaluation import evaluate_run
from bdc_soi.review_package import build_review_workbook, import_review, stable_annotation_id
from tests.conftest import SYN_ACCESSION, SYN_CIK
from tests.integration.test_pipeline_synthetic import run_result  # noqa: F401 (shared module fixture)


def test_workbook_export_import_and_sample_scoped_evaluation(run_result, tmp_path):
    ctx, r, out, manifest = run_result
    wb = tmp_path / "review.xlsx"
    info = build_review_workbook([out], wb, per_company=4)
    assert info["review_rows"] >= 4 and info["summary_rows"] == 1
    batch = pd.read_excel(wb, sheet_name="review_batch", dtype=str).fillna("")
    assert set(batch.sample_stratum.map(lambda s: s.split(":")[0])) >= {"ordinary_high_confidence", "method"} or len(batch) == 5
    assert (batch.reviewer_decision == "").all() and (batch.reviewer_name == "").all()
    assert batch.sec_document_url.iloc[0].startswith("https://www.sec.gov/Archives/edgar/data/999999999/000999999925000001/")
    assert batch.annotation_id.iloc[0] == stable_annotation_id(SYN_ACCESSION, batch.holding_id.iloc[0])
    for col in ("proposed_fair_value", "corrected_fair_value", "reporting_currency_selected", "xbrl_fair_value_unit_original", "principal_currency", "corrected_reporting_currency", "reconciliation_scope", "scope_rule", "identity_resolution", "conflict_classes"):
        assert col in batch.columns, col
    # Invalid import: a decision without a name must be rejected and nothing written.
    golden = tmp_path / "golden"
    (golden / "manifests").mkdir(parents=True)
    (golden / "manifests" / f"{SYN_ACCESSION}.yml").write_text(f"cik: '{SYN_CIK}'\naccession_number: '{SYN_ACCESSION}'\nsplit: development\nreview_status: unreviewed\n")
    batch.loc[0, "reviewer_decision"] = "approve"
    batch.to_excel(tmp_path / "bad.xlsx", sheet_name="review_batch", index=False)
    bad = import_review(tmp_path / "bad.xlsx", golden)
    assert bad["problems"] and not (golden / "expected").exists()
    # Valid import: one approve, one correct (fair value), one reject; the rest untouched.
    batch.loc[0, ["reviewer_decision", "reviewer_name", "review_date"]] = ["approve", "Reviewer A", "2026-10-06"]
    batch.loc[1, ["reviewer_decision", "reviewer_name", "review_date", "corrected_fair_value"]] = ["correct", "Reviewer A", "2026-10-06", "999.0"]
    batch.loc[2, ["reviewer_decision", "reviewer_name", "review_date"]] = ["reject", "Reviewer A", "2026-10-06"]
    batch.to_excel(tmp_path / "good.xlsx", sheet_name="review_batch", index=False)
    good = import_review(tmp_path / "good.xlsx", golden)
    assert good["problems"] == [] and good["accepted_rows"] == 3
    exp = pd.read_csv(golden / "expected" / f"{SYN_ACCESSION}.csv", dtype=str, keep_default_na=False)
    assert len(exp) == 3 and set(exp.decision) == {"approve", "correct", "reject"} and exp[exp.decision == "correct"].fair_value.iloc[0] == "999.0"
    m = yaml.safe_load((golden / "manifests" / f"{SYN_ACCESSION}.yml").read_text())
    assert m["review_status"] == "reviewed" and m["review_scope"] == "sample" and m["reviewer"] == "Reviewer A" and m["split"] == "development"
    rep = evaluate_run(out, golden, tmp_path / "rep")
    assert rep.reviewed_filings == 1 and rep.row_metrics["tp"] == 2 and rep.row_metrics["fp"] == 1  # rejected row present -> FP
    assert rep.field_metrics["fair_value"]["normalized_accuracy"] == 0.5 and any("sample-scoped" in n for n in rep.notes)


def test_triage_profile_is_small_and_keeps_blocker_inventory_separate(run_result, tmp_path):
    from bdc_soi.review_package import blocker_inventory

    ctx, r, out, manifest = run_result
    wb = tmp_path / "triage.xlsx"
    info = build_review_workbook([out], wb, per_company=2, profile="triage", blocker_budget=3)
    batch = pd.read_excel(wb, sheet_name="review_batch", dtype=str).fillna("")
    strata = batch.sample_stratum.map(lambda s: s.split(":")[0]).tolist()
    assert len(batch) <= 2 + 3 and strata.count("blocker") <= 3 and "ordinary_high_confidence" in strata or "ordinary_any" in strata
    assert (batch.reviewer_decision == "").all() and (batch.reviewer_name == "").all() and (batch.review_date == "").all()
    inv = blocker_inventory([out])
    assert set(inv.columns) >= {"annotation_id", "holding_id", "identity_flags", "review_flags", "field_conflicts"}
    instr = pd.read_excel(wb, sheet_name="instructions", header=None, dtype=str).fillna("")
    assert instr.apply(lambda col: col.str.contains("triage").any()).any()


def test_unresolved_decision_is_logged_but_never_becomes_a_golden_label(run_result, tmp_path):
    from bdc_soi.review_package import import_review

    ctx, r, out, manifest = run_result
    wb = tmp_path / "review.xlsx"
    build_review_workbook([out], wb, per_company=4)
    batch = pd.read_excel(wb, sheet_name="review_batch", dtype=str).fillna("")
    batch.loc[0, "reviewer_decision"] = "unresolved"
    batch.loc[0, "reviewer_name"] = "Reviewer"
    batch.loc[0, "review_date"] = "2026-10-06"
    batch.loc[0, "reviewer_comment"] = "identity contradiction between the sources"
    with pd.ExcelWriter(wb, engine="openpyxl", mode="a", if_sheet_exists="replace") as w:
        batch.to_excel(w, sheet_name="review_batch", index=False)
    golden = tmp_path / "golden"
    res = import_review(wb, golden, today=date(2026, 10, 7))
    assert res["problems"] == [] and res["accepted_rows"] == 0 and res["unresolved_rows"] == 1
    assert not (golden / "expected").exists() or not list((golden / "expected").glob("*.csv"))
    assert not (golden / "manifests").exists() or not list((golden / "manifests").glob("*.yml"))
    log = list((golden / "review_log").glob("*.unresolved.csv"))
    assert len(log) == 1 and pd.read_csv(log[0], dtype=str).decision.iloc[0] == "unresolved"
