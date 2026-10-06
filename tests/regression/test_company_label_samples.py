"""Regression guard for every company template's composite rules against label samples copied from the cited
filings (tests/fixtures/company_label_samples.json). The expected fields are engine-derived (2026-10-06), not
reviewed golden values; a change here must be explained in docs/iteration-log.md."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from bdc_soi.composite_parser import apply_composite_rule
from bdc_soi.templates import load_template_file

ROOT = Path(__file__).resolve().parents[2]
DATA = json.loads((ROOT / "tests" / "fixtures" / "company_label_samples.json").read_text())
CASES = [(c["cik"], c["template_id"], s) for c in DATA["companies"] for s in c["samples"]]


@pytest.mark.parametrize("cik,template_id,sample", CASES, ids=[f"{c}:{s['rule_id']}:{i}" for i, (c, _t, s) in enumerate(CASES)])
def test_company_composite_rule_reproduces_sample(cik: str, template_id: str, sample: dict) -> None:
    lt = load_template_file(ROOT / "templates" / f"{cik}.yml")
    assert lt.issues == []
    tv = lt.file.templates[0]
    assert tv.id == template_id
    rule = next(r for r in tv.composite_fields if r.id == sample["rule_id"])
    res = apply_composite_rule(rule, sample["label"], tv.normalization)
    assert res.matched
    got = {k: (v.value.isoformat() if isinstance(v.value, date) else v.value) for k, v in res.fields.items()}
    for field, expected in sample["fields"].items():
        assert got.get(field) == expected, (field, got.get(field), expected)


def test_every_universe_company_has_a_template_covering_its_latest_report_date() -> None:
    import yaml

    from bdc_soi.templates import TemplateRegistry

    reg = TemplateRegistry.from_directory(ROOT / "templates")
    reg.raise_if_invalid()
    universe = yaml.safe_load((ROOT / "config" / "bdc_universe.yml").read_text())
    assert len(universe["companies"]) == 26
    for c in DATA["companies"]:
        tv, reason = reg.select(c["cik"], date.fromisoformat(c["report_date"]), "10-Q", c["accession"])
        assert tv is not None and tv.id == c["template_id"], (c["cik"], reason)


def test_triplepoint_grand_total_row_is_the_total_and_cash_equivalents_follow_it():
    # 0001580345-26-000025 table_25: 'Total Investments in Portfolio Companies - 221.28%*(9)(11) $ 830,835 $ 780,742'
    # is the schedule total (equal to the undimensioned XBRL totals); the 'Cash Equivalents' money-market row follows it.
    import re
    lt = load_template_file(ROOT / "templates" / "1580345.yml")
    rules = lt.file.templates[0].html.row_rules
    assert any(re.search(p, "Total Investments in Portfolio Companies - 221.28%*(9)(11)") for p in rules.total_if_regex)
    assert not any(re.search(p, "Total Investments in Affiliates") for p in rules.total_if_regex)


PRIOR_REPORT_DATES = {cik: "2026-03-31" for cik in ["1950976", "1837532", "1633858", "1950572", "1379785", "1843162", "1841514", "1633336", "1476765", "1572694", "1901612", "1578348", "1959604", "1747172", "1779523", "1925531", "1860424", "1905824", "1794776", "1743415", "1832148", "1932591", "1901037", "1580345", "2020354"]}
PRIOR_REPORT_DATES["2018545"] = "2025-03-31"  # Franklin BSP: no 10-Q after 2025-06-30 within the lookback


def test_every_universe_company_has_a_template_covering_its_prior_report_date() -> None:
    # Audax's template started at 2026-06-30, so its 2026-03-31 10-Q fell back to the generic template (HTML: no rows).
    from datetime import date

    missing = []
    for cik, rd in PRIOR_REPORT_DATES.items():
        lt = load_template_file(ROOT / "templates" / f"{cik}.yml")
        d = date.fromisoformat(rd)
        chosen = [t for t in lt.file.templates if t.effective_from <= d and (t.effective_to is None or t.effective_to >= d)]
        if not chosen:
            missing.append((cik, rd))
    assert missing == [], missing


def test_triplepoint_affiliation_segment_is_not_an_investment_type() -> None:
    # 0001580345-26-000021: debt labels are 'Issuer | Description | Non-Affiliated' (third segment = affiliation); the
    # positional rule wrote 'Non-Affiliated' into investment_type for 101 rows.
    lt = load_template_file(ROOT / "templates" / "1580345.yml")
    tv = lt.file.templates[0]
    rule = next(r for r in tv.composite_fields if r.id == "tpvg-pipe-label-v1")
    res = apply_composite_rule(rule, "Lively, Inc. | Growth Capital Loan | Non-Affiliated", tv.normalization)
    got = {k: v.value for k, v in res.fields.items()}
    assert got.get("investment_type") in (None, "") and got.get("affiliate_status") == "Non-Affiliated"
