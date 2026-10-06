import json
from datetime import date
from pathlib import Path

import pytest
import yaml

from bdc_soi.templates import TemplateFile, TemplateRegistry, TemplateValidationError, load_template_file, template_json_schema, validate_template_file
from tests.conftest import ROOT

BASE = {"schema_version": 1, "cik": "0001234567", "company_name": "T"}


def _tf(templates):
    return TemplateFile.model_validate({**BASE, "templates": templates})


def _tv(id, start, end=None, **kw):
    return {"id": id, "effective_from": start, "effective_to": end, **kw}


def test_committed_json_schema_matches_model():
    committed = json.loads((ROOT / "config" / "template.schema.json").read_text())
    assert committed == template_json_schema()


def test_alias_fields_are_canonicalized():
    tf = _tf([_tv("a", "2025-01-01", xbrl={"field_concepts": {"issuer_name": ["us-gaap:X"], "security_description": ["Y"]}}, html={"header_aliases": {"issuer_name": ["^Issuer$"]}}, overrides=[{"id": "o1", "match": {"report_date": "2025-06-30", "raw_issuer_name": "Exact text"}, "set": {"issuer_name": "Fixed"}, "provenance": {"source_type": "filing_footnote", "source_reference": "p1", "reviewed_by": "reviewer@acme.test", "reviewed_at": "2025-07-01", "rationale": "x"}}])])
    t = tf.templates[0]
    assert set(t.xbrl.field_concepts) == {"issuer", "description"} and "issuer" in t.html.header_aliases
    assert t.overrides[0].match.issuer_name_raw == "Exact text" and t.overrides[0].set == {"issuer": "Fixed"}
    assert validate_template_file(tf) == []


def test_overlap_rejected_only_when_ambiguous():
    amb = _tf([_tv("a", "2025-01-01", "2025-12-31"), _tv("b", "2025-06-01", "2026-05-31")])
    assert any("overlap ambiguously" in i for i in validate_template_file(amb))
    ok_priority = _tf([_tv("a", "2025-01-01", "2025-12-31", priority=1), _tv("b", "2025-06-01", "2026-05-31", priority=2)])
    assert validate_template_file(ok_priority) == []
    ok_narrow = _tf([_tv("a", "2025-01-01", None), _tv("b", "2025-06-01", "2025-09-30")])
    assert validate_template_file(ok_narrow) == []
    ok_acc = _tf([_tv("a", "2025-01-01", "2025-12-31"), _tv("b", "2025-06-01", "2026-05-31", accessions=["0001234567-25-000001"])])
    assert validate_template_file(ok_acc) == []


def test_selection_rules():
    tf = _tf([_tv("wide", "2020-01-01", None, priority=1), _tv("narrow", "2025-01-01", "2025-12-31"), _tv("acc", "2025-01-01", "2025-12-31", accessions=["0001234567-25-000009"]), _tv("old", "2020-01-01", "2023-12-31", forms=["10-K"])])
    from bdc_soi.templates import LoadedTemplate

    reg = TemplateRegistry([LoadedTemplate(Path("1234567.yml"), tf, "x", [])])
    assert reg.select("1234567", date(2025, 6, 30))[0].id == "narrow"
    assert reg.select("1234567", date(2025, 6, 30), accession="0001234567-25-000009")[0].id == "acc"
    assert reg.select("1234567", date(2026, 6, 30))[0].id == "wide"
    assert reg.select("1234567", date(2025, 12, 31))[0].id == "narrow"  # inclusive boundary
    assert reg.select("1234567", date(2026, 1, 1))[0].id == "wide"  # day after boundary
    assert reg.select("1234567", date(2021, 1, 1), form="10-Q")[0].id == "wide"
    assert reg.select("1234567", date(2021, 1, 1), form="10-K")[0].id == "old"
    assert reg.select("9999", date(2025, 1, 1)) == (None, "no_company_template_file")
    tied = _tf([_tv("a", "2025-01-01", "2025-12-31"), _tv("b", "2025-01-01", "2025-12-31")])
    assert any("overlap ambiguously" in i for i in validate_template_file(tied))
    reg2 = TemplateRegistry([LoadedTemplate(Path("1234567.yml"), tied, "x", [])])
    with pytest.raises(TemplateValidationError):
        reg2.select("1234567", date(2025, 6, 30))


def test_rejections():
    bad_regex = _tf([_tv("a", "2025-01-01", xbrl={"role_regex": ["("]})])
    assert any("does not compile" in i for i in validate_template_file(bad_regex))
    unknown_field = _tf([_tv("a", "2025-01-01", xbrl={"field_concepts": {"not_a_field": ["X"]}})])
    assert any("unknown canonical field" in i for i in validate_template_file(unknown_field))
    with pytest.raises(Exception):
        _tf([_tv("a", "2025-01-01", overrides=[{"id": "o", "match": {"report_date": "2025-06-30", "raw_issuer_name": "x"}, "set": {"issuer": "y"}}])])  # no provenance
    placeholder = _tf([_tv("a", "2025-01-01", xbrl={"field_concepts": {"fair_value": ["{issuer-namespace}FV"]}})])
    assert any("placeholder" in i for i in validate_template_file(placeholder))
    scale = _tf([_tv("a", "2025-01-01", html={"scale": {"source": "fixed"}})])
    assert any("fixed_multiplier" in i for i in validate_template_file(scale))
    dup = _tf([_tv("a", "2025-01-01", "2025-06-30"), _tv("a", "2025-07-01")])
    assert any("duplicate template id" in i for i in validate_template_file(dup))
    conflict = _tf([_tv("a", "2025-01-01", html={"row_rules": {"skip_if_regex": ["^Total Investments"], "total_if_regex": ["^Total Investments"]}})])
    assert any("row rule conflicts with total rule" in i for i in validate_template_file(conflict))
    malformed = _tf([_tv("a", "2025-01-01", xbrl={"row_axes": {"explicit_qnames": ["{bad"]}})])
    assert any("malformed" in i for i in validate_template_file(malformed))
    unit = _tf([_tv("a", "2025-01-01", composite_fields=[{"id": "c", "source_field": "issuer", "pattern": "(?P<rate>.+)", "rate_parser": {"pattern": "(?P<index>S)\\+(?P<spread>\\d+)"}}])])
    assert any("spread_unit" in i for i in validate_template_file(unit))


def test_placeholder_templates_are_never_selected():
    tf = _tf([_tv("ph", "2025-01-01", status="placeholder", xbrl={"field_concepts": {"fair_value": ["{issuer-namespace}FV"]}})])
    assert validate_template_file(tf) == []
    from bdc_soi.templates import LoadedTemplate

    reg = TemplateRegistry([LoadedTemplate(Path("1234567.yml"), tf, "x", [])])
    t, reason = reg.select("1234567", date(2025, 6, 30))
    assert t is None and reason.startswith("only_placeholder_templates")


def test_repository_templates_are_valid():
    reg = TemplateRegistry.from_directory(ROOT / "templates")
    assert reg.issues == []
    for lt in reg.loaded:
        assert lt.file.cik == "generic" or lt.file.cik.isdigit()


def test_delimited_rule_and_total_preference_validation():
    ok = _tf([_tv("a", "2025-01-01", composite_fields=[{"id": "d", "source_field": "issuer", "kind": "delimited", "delimiter": "|", "positions": {"issuer": 0, "description": 1}}], validation={"total_source_preference": ["html_template_total"], "total_source_preference_evidence": "HTML total equals holdings; XBRL undimensioned fact includes cash equivalents"})])
    assert validate_template_file(ok) == []
    bad = _tf([_tv("a", "2025-01-01", composite_fields=[{"id": "d", "source_field": "issuer", "kind": "delimited", "positions": {"nonsense": 0}}], validation={"total_source_preference": ["bogus"]})])
    issues = validate_template_file(bad)
    assert any("delimiter" in i for i in issues) and any("no canonical target" in i for i in issues) and any("unknown source" in i for i in issues) and any("evidence" in i for i in issues)
