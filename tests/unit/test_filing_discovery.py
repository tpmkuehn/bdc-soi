import json
from datetime import date
from pathlib import Path

from bdc_soi.config import FilingsConfig, SecConfig
from bdc_soi.filing_discovery import classify_filings, discover_filings, parse_submissions_block
from bdc_soi.sec_client import SecClient
from tests.conftest import SYN


def test_parse_and_classify_submissions():
    data = json.loads((SYN / "submissions" / "CIK0999999999.json").read_text())
    recs = parse_submissions_block("999999999", data["name"], data["filings"]["recent"], "CIK0999999999.json")
    assert len(recs) == 3
    classify_filings(recs, FilingsConfig(months_back=18, eligible_forms=["10-Q"], use_amendments=False), date(2026, 10, 6))
    by_acc = {r.accession_number: r for r in recs}
    assert by_acc["0009999999-25-000001"].selected and by_acc["0009999999-25-000001"].reason == "selected_latest_eligible"
    assert "amendment_excluded" in by_acc["0009999999-25-000002"].reason
    assert "older_than_lookback" in by_acc["0009999999-24-000009"].reason


def test_amendments_can_be_enabled():
    data = json.loads((SYN / "submissions" / "CIK0999999999.json").read_text())
    recs = parse_submissions_block("999999999", None, data["filings"]["recent"], "x")
    classify_filings(recs, FilingsConfig(use_amendments=True), date(2026, 10, 6))
    selected = [r for r in recs if r.selected][0]
    assert selected.form == "10-Q/A"  # later filing date wins


def test_illustrative_accession_never_eligible():
    recs = parse_submissions_block("1", None, {"accessionNumber": ["0000000000-26-000001"], "filingDate": ["2026-09-01"], "reportDate": ["2026-06-30"], "form": ["10-Q"], "primaryDocument": ["x.htm"]}, "x")
    classify_filings(recs, FilingsConfig(), date(2026, 10, 6))
    assert not recs[0].eligible and "illustrative_accession" in recs[0].reason


def test_discover_from_cache_offline(tmp_path: Path):
    sub = tmp_path / "sec" / "submissions"
    sub.mkdir(parents=True)
    (sub / "CIK0999999999.json").write_bytes((SYN / "submissions" / "CIK0999999999.json").read_bytes())
    client = SecClient(SecConfig(user_agent=None), tmp_path, offline=True)
    res = discover_filings(client, "999999999", FilingsConfig(), date(2025, 10, 6))
    assert res.company_name == "Synthetic Test BDC" and res.selected.accession_number == "0009999999-25-000001"
