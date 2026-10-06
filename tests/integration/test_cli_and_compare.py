from pathlib import Path

import pandas as pd

from bdc_soi.cli import main
from bdc_soi.compare import compare_runs
from tests.conftest import ROOT


def test_validate_templates_cli(capsys):
    assert main(["validate-templates", "--templates", str(ROOT / "templates"), "--schema", str(ROOT / "config" / "template.schema.json")]) == 0
    assert "OK" in capsys.readouterr().out


def test_validate_templates_cli_fails_on_bad_template(tmp_path, capsys):
    (tmp_path / "bad.yml").write_text("schema_version: 1\ncik: '1'\ntemplates:\n  - id: a\n    effective_from: 2025-01-01\n    xbrl:\n      role_regex: ['(']\n")
    assert main(["validate-templates", "--templates", str(tmp_path), "--schema", str(ROOT / "config" / "template.schema.json")]) == 1


def test_extract_refuses_illustrative_accession(tmp_path):
    assert main(["extract", "--cik", "1837532", "--accession", "0000000000-26-000001", "--output", str(tmp_path / "o")]) == 2


def test_compare_runs(tmp_path):
    before, after = tmp_path / "b", tmp_path / "a"
    before.mkdir(); after.mkdir()
    cols = ["holding_id", "accession_number", "issuer", "fair_value", "field_lineage", "extraction_confidence", "review_flags"]
    pd.DataFrame([["h1", "acc", "A", 1, '{"issuer": {"source": "xbrl_fact"}}', 0.8, "[]"], ["h2", "acc", "B", 2, "{}", 0.7, "[]"]], columns=cols).to_csv(before / "holdings.csv", index=False)
    pd.DataFrame([["h1", "acc", "A", 3, '{"issuer": {"source": "html_cell"}}', 0.6, '["x"]'], ["h3", "acc", "C", 2, "{}", 0.7, "[]"]], columns=cols).to_csv(after / "holdings.csv", index=False)
    pd.DataFrame([["acc", "fair_value", "pass"]], columns=["accession_number", "field", "status"]).to_csv(before / "validation.csv", index=False)
    pd.DataFrame([["acc", "fair_value", "fail"]], columns=["accession_number", "field", "status"]).to_csv(after / "validation.csv", index=False)
    s = compare_runs(before, after, tmp_path / "cmp")
    assert s["rows_added"] == 1 and s["rows_removed"] == 1 and s["field_changes"] == 1 and s["lineage_changes"] == 1 and s["confidence_changes"] == 1 and s["review_flag_changes"] == 1
    assert s["reconciliation_changes"][0]["after"] == "fail" and s["material_deterioration"]
    assert (tmp_path / "cmp" / "field_changes.csv").exists()
