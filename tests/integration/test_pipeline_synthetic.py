"""Offline end-to-end run on the synthetic fixture (SPEC 22.3)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from bdc_soi.output import REQUIRED_ARTIFACTS, OutputExistsError, prepare_output_dir, write_run
from bdc_soi.pipeline import process_filing
from tests.conftest import ROOT as ROOT_PATH, SYN_ACCESSION, SYN_CIK

ROOT_TEMPLATES = ROOT_PATH / "templates"


@pytest.fixture(scope="module")
def run_result(tmp_path_factory, request):
    from tests.conftest import ROOT, stage_synthetic_package
    import shutil
    from bdc_soi.config import load_config
    from bdc_soi.pipeline import RunContext
    from bdc_soi.sec_client import SecClient
    from bdc_soi.templates import TemplateRegistry

    tmp = tmp_path_factory.mktemp("run")
    cache = tmp / "cache"
    stage_synthetic_package(cache)
    if (ROOT / "cache" / "arelle").exists():
        shutil.copytree(ROOT / "cache" / "arelle", cache / "arelle", dirs_exist_ok=True)
    tdir = tmp / "templates"
    tdir.mkdir()
    shutil.copy(ROOT / "templates" / "generic.yml", tdir / "generic.yml")
    shutil.copy(ROOT / "tests" / "fixtures" / "synthetic" / "templates" / "999999999.yml", tdir / "999999999.yml")
    cfg = load_config(ROOT / "config" / "application.yml", {"paths.cache": str(cache), "paths.templates": str(tdir), "extraction.offline": True})
    cfg.sec.user_agent = "bdc_soi/0.0 analyst@acme.test"  # synthetic contact: must never appear in any artifact
    cfg.sec.user_agent_source = "cli"
    reg = TemplateRegistry.from_directory(tdir)
    reg.raise_if_invalid()
    ctx = RunContext(config=cfg, registry=reg, client=SecClient(cfg.sec, cache, offline=True), cache_dir=cache, offline=True)
    result = process_filing(ctx, SYN_CIK, SYN_ACCESSION)
    out = tmp / "out1"
    manifest = write_run(ctx, [result], out, started=datetime.now(timezone.utc), run_id="test-run", command="extract")
    return ctx, result, out, manifest


def test_pipeline_produces_holdings_and_reconciles(run_result):
    ctx, r, out, manifest = run_result
    d = r.diagnostic
    assert d.status == "ok", d.errors
    assert d.xbrl_status == "ok" and d.html_status == "ok" and d.instance_kind == "extracted_instance"
    assert d.template_id == "synthetic-bdc-2025-v1"
    assert d.holdings_count == 5 and d.xbrl_holdings == 5 and d.html_rows == 5 and d.matched_rows == 5 and d.unmatched_html_rows == 0
    assert d.fair_value_reconciliation == "pass" and d.cost_reconciliation == "pass"
    by_desc = {(h.issuer, h.description): h for h in r.holdings}
    tl = by_desc[("Redwood Runway Bidco LLC", "First Lien Secured Debt - Term Loan")]
    assert tl.industry == "Software" and tl.reference_index == "SOFR" and tl.spread == 0.045 and tl.spread_bps == 450 and tl.rate_floor == 0.005
    assert tl.maturity_date.isoformat() == "2031-12-17" and tl.principal_amount == 10_000_000 and tl.cost == 9_900_000 and tl.fair_value == 10_050_000
    assert tl.issue_date is None and tl.source_method == "hybrid_xbrl_html" and tl.currency == "USD"
    assert tl.field_lineage["issuer"].source == "parsed_composite_text" and tl.field_lineage["issuer"].rule_id == "member-label-layout-v1"
    assert tl.field_lineage["fair_value"].source == "xbrl_fact" and tl.field_lineage["spread"].source == "xbrl_fact"
    # The template excludes fair-value-hierarchy contexts, so the duplicate FV fact never competes.
    assert not any(c.field == "fair_value" for c in tl.field_conflicts) and "i_2025_h1_dup" not in tl.source_context_ids
    assert tl.issuer_name_raw.startswith("Software Redwood Runway Bidco, LLC Investment Type")
    rc = by_desc[("Redwood Runway Bidco LLC", "First Lien Secured Debt - Revolver")]
    assert rc.holding_id != tl.holding_id and rc.fair_value == 2_000_000 and rc.rate_floor == 0.005
    eq = by_desc[("Alpine Health Services Inc", "Common Equity")]
    assert eq.maturity_date is None and eq.shares == 1000.0 and eq.field_lineage["shares"].source == "html_cell" and eq.fair_value == 650_000
    assert all(h.holding_id and len(h.holding_id) == 32 for h in r.holdings)
    assert all(f in h.field_lineage for h in r.holdings for f in ("issuer", "fair_value"))
    recon = {x.field: x for x in r.reconciliations}
    assert recon["fair_value"].reported_total == 22_450_000 and recon["fair_value"].selected_source == "xbrl_no_dimensions"
    assert recon["cost"].reported_total == 22_280_000
    assert all(h.extraction_confidence >= 0.5 for h in r.holdings)


def test_all_required_artifacts_written(run_result):
    ctx, r, out, manifest = run_result
    for name in REQUIRED_ARTIFACTS:
        assert (out / name).exists(), name
    df = pd.read_csv(out / "holdings.csv")
    assert "issuer" in df.columns and "description" in df.columns and "issuer_name" not in df.columns and "security_description" not in df.columns
    assert len(df) == 5
    assert manifest["row_counts"]["holdings"] == 5 and manifest["template_checksums"] and manifest["configuration_checksum"]
    assert manifest["selected_filings"][0]["accession_checksums"]
    manifest_text = json.dumps(manifest)
    assert "analyst@acme.test" not in manifest_text and manifest["configuration"]["sec"]["user_agent"] == "<redacted>"
    assert manifest["configuration"]["sec"]["user_agent_source"] == "cli"  # provenance without the contact itself
    assert "analyst@acme.test" not in (out / "run_manifest.json").read_text(encoding="utf-8")
    assert not any("analyst@acme.test" in p.read_text(encoding="utf-8", errors="ignore") for p in out.iterdir() if p.suffix in {".csv", ".json", ".md", ".txt"})
    pq = pd.read_parquet(out / "holdings.parquet")
    assert len(pq) == 5
    assert (out / "long_xbrl_facts.parquet").stat().st_size > 0 and len(pd.read_parquet(out / "long_xbrl_facts.parquet")) == 31


def test_output_dir_is_not_clobbered(run_result):
    ctx, r, out, manifest = run_result
    with pytest.raises(OutputExistsError):
        prepare_output_dir(out)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_cached_rerun_is_deterministic(run_result):
    ctx, r, out, manifest = run_result
    r2 = process_filing(ctx, SYN_CIK, SYN_ACCESSION)
    out2 = out.parent / "out2"
    write_run(ctx, [r2], out2, started=datetime.now(timezone.utc), run_id="test-run-2", command="extract")
    for name in ("holdings.csv", "holdings.parquet", "holdings.json", "validation.csv", "matching_diagnostics.csv", "axis_diagnostics.csv", "html_table_diagnostics.csv", "review_queue.csv", "long_xbrl_facts.parquet", "all_filings.parquet", "template_usage.csv", "output.xlsx"):
        assert _digest(out / name) == _digest(out2 / name), name
    m1 = json.loads((out / "run_manifest.json").read_text())
    m2 = json.loads((out2 / "run_manifest.json").read_text())
    for k in m1["nondeterministic_fields"]:
        m1.pop(k, None)
        m2.pop(k, None)
    m1.pop("command", None); m2.pop("command", None)
    assert m1 == m2


def test_html_failure_retains_xbrl_results(run_result, monkeypatch):
    ctx, r, out, manifest = run_result
    import bdc_soi.pipeline as pl

    def boom(*a, **k):
        raise RuntimeError("synthetic html failure")

    monkeypatch.setattr(pl, "extract_html", boom)
    r2 = process_filing(ctx, SYN_CIK, SYN_ACCESSION)
    assert r2.diagnostic.html_status == "failed" and r2.diagnostic.xbrl_status == "ok" and len(r2.holdings) == 5
    assert r2.diagnostic.status == "partial" and r2.errors[0].phase == "html_table_detection" and "synthetic html failure" in r2.errors[0].message
    assert all(h.source_method == "xbrl" for h in r2.holdings)


def test_xbrl_failure_retains_html_fallback(run_result, monkeypatch):
    ctx, r, out, manifest = run_result
    import bdc_soi.pipeline as pl

    def boom(*a, **k):
        raise RuntimeError("synthetic arelle failure")

    monkeypatch.setattr(pl, "load_model", boom)
    r2 = process_filing(ctx, SYN_CIK, SYN_ACCESSION)
    assert r2.diagnostic.xbrl_status.startswith("failed") and r2.diagnostic.html_status == "ok"
    assert len(r2.holdings) == 5 and all(h.source_method == "html_only" for h in r2.holdings)
    assert all(h.extraction_confidence <= 0.60 for h in r2.holdings)
    h = next(x for x in r2.holdings if x.description == "First Lien Secured Debt - Term Loan" and x.issuer == "Redwood Runway Bidco LLC")
    assert h.reference_index == "SOFR" and h.spread_bps == 450 and h.rate_floor == 0.005 and h.fair_value == 10_050_000


def test_review_queue_and_evaluation_on_unreviewed_candidates(run_result, tmp_path):
    from bdc_soi.evaluation import evaluate_run, write_candidate_annotations

    ctx, r, out, manifest = run_result
    golden = tmp_path / "golden"
    (golden / "manifests").mkdir(parents=True)
    path = write_candidate_annotations(out, golden, SYN_ACCESSION)
    df = pd.read_csv(path)
    assert (df["review_status"] == "unreviewed").all() and len(df) == 5
    (golden / "manifests" / f"{SYN_ACCESSION}.yml").write_text(f"cik: '{SYN_CIK}'\naccession_number: '{SYN_ACCESSION}'\nsplit: development\nreview_status: unreviewed\nexpected_file: ../annotations/{SYN_ACCESSION}.candidates.csv\n")
    rep = evaluate_run(out, golden, tmp_path / "report")
    assert rep.reviewed_filings == 0 and rep.acceptance["holding_row_precision"]["status"] == "NOT ASSESSED"
    rep2 = evaluate_run(out, golden, tmp_path / "report2", include_unreviewed=True)
    assert rep2.row_metrics["row_precision"] == 1.0 and rep2.row_metrics["row_recall"] == 1.0
    assert rep2.acceptance["holding_row_precision"]["status"] == "NOT ASSESSED"  # unreviewed never counts
    assert rep2.field_metrics["fair_value"]["normalized_accuracy"] == 1.0


def test_composite_no_match_flag_only_when_no_rule_matches():
    from bdc_soi.models import Holding
    from bdc_soi.pipeline import apply_composites_to_holding
    from bdc_soi.templates import CompositeField, TemplateVersion

    rules = [
        CompositeField(id="v1", source_field="issuer", pattern=r"^(?P<header>.+?)\s+Investment Type\s+(?P<description>.+)$"),
        CompositeField(id="v2", source_field="issuer", pattern=r"^(?P<header>.+?)\s+(?P<description>(?:First|Second) Lien Secured Debt - .+?)\s+Maturity Date\s+(?P<maturity>\d{1,2}/\d{1,2}/\d{4})$"),
    ]
    tv = TemplateVersion(id="t", effective_from="2025-01-01", composite_fields=rules)
    h = Holding(cik="1", accession_number="0000000001-25-000001", issuer_name_raw="Acme Corp First Lien Secured Debt - Term Loan Maturity Date 9/30/2030")
    h.set_field("issuer", "Acme Corp First Lien ...", source="xbrl_dimension_member")
    apply_composites_to_holding(h, rules, tv)
    assert h.description == "First Lien Secured Debt - Term Loan" and h.issuer == "Acme Corp" and h.field_lineage["issuer"].rule_id == "v2"
    assert not any(f.startswith("composite_no_match") for f in h.review_flags)
    h2 = Holding(cik="1", accession_number="0000000001-25-000001", issuer_name_raw="Unparseable label")
    h2.set_field("issuer", "Unparseable label", source="xbrl_dimension_member")
    apply_composites_to_holding(h2, rules, tv)
    assert any(f.startswith("composite_no_match") for f in h2.review_flags)


def test_html_rate_cells_are_coerced_with_template_aliases():
    from bdc_soi.pipeline import coerce_html_rate_fields
    from bdc_soi.templates import TemplateVersion

    tv = TemplateVersion(id="t", effective_from="2025-01-01", normalization={"reference_index_aliases": {"S": "SOFR"}})
    out = coerce_html_rate_fields({"reference_index": "S+", "spread": "5.00%", "interest_rate": "8.73%"}, tv)
    assert out["reference_index"] == "SOFR" and out["spread"] == 0.05 and out["spread_bps"] == 500 and out["interest_rate"] == 0.0873
    out2 = coerce_html_rate_fields({"reference_index": "S+", "interest_rate": "S+425, 0.50% Floor"}, None)
    assert out2["reference_index"] is None and out2["interest_rate_text"] == "S+425, 0.50% Floor"  # no global S=SOFR assumption


def test_template_industry_vocabulary_recognised_in_html_headings(run_result):
    # The synthetic template lists Software/Healthcare as known industries; both headings must map to industry
    # even though the instance also carries an industry axis.
    ctx, r, out, manifest = run_result
    assert {h.industry for h in r.holdings} == {"Software", "Healthcare"}
    assert all(h.field_lineage["industry"].source in {"parsed_composite_text", "xbrl_dimension_member"} for h in r.holdings)


def test_template_can_disable_html_with_reason(run_result, tmp_path):
    import shutil
    import yaml
    from bdc_soi.templates import TemplateRegistry

    ctx, r, out, manifest = run_result
    tdir = tmp_path / "templates"
    tdir.mkdir()
    shutil.copy(ROOT_TEMPLATES / "generic.yml", tdir / "generic.yml")
    data = yaml.safe_load((ROOT_TEMPLATES.parent / "tests" / "fixtures" / "synthetic" / "templates" / "999999999.yml").read_text())
    data["templates"][0]["html"]["disabled"] = True
    data["templates"][0]["html"]["disabled_reason"] = "synthetic: layout unsupported"
    (tdir / "999999999.yml").write_text(yaml.safe_dump(data))
    reg = TemplateRegistry.from_directory(tdir)
    reg.raise_if_invalid()
    from dataclasses import replace

    ctx2 = replace(ctx, registry=reg)
    r2 = process_filing(ctx2, SYN_CIK, SYN_ACCESSION)
    assert r2.diagnostic.html_status == "disabled_by_template" and "html_disabled_by_template" in r2.filing_flags
    assert len(r2.holdings) == 5 and all(h.source_method == "xbrl" for h in r2.holdings) and not r2.errors
