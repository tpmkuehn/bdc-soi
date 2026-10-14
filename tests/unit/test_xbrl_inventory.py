from datetime import date
from pathlib import Path

import pytest

from bdc_soi.xbrl_inventory import build_inventory, dimension_signature
from bdc_soi.xbrl_loader import load_model
from tests.conftest import ROOT, SYN


def test_dimension_signature_is_sorted_and_complete():
    dims = {"{b}Axis": "{b}M", "{a}Axis": "typed:Some Value"}
    assert dimension_signature(dims) == "{a}Axis=typed:Some Value|{b}Axis={b}M"


@pytest.fixture(scope="module")
def inventory():
    loaded = load_model(SYN / "package" / "syn-20250630_htm.xml", ROOT / "cache", offline=True)  # offline: no contact, no taxonomy download
    inv = build_inventory(loaded.model, loaded.document_type, loaded.extension_namespaces)
    loaded.close()
    return inv


def test_inventory_completeness(inventory):
    assert inventory.report_date == date(2025, 6, 30) and inventory.report_date_source == "dei:DocumentPeriodEndDate"
    assert len(inventory.facts) == 31
    f = next(x for x in inventory.facts if x.fact_id == "h1f")
    assert f.period_type == "instant" and f.period_end == date(2025, 6, 30)
    assert f.numeric_value == 10050000.0 and f.unit == "USD" and f.decimals == "-3" and not f.is_nil
    assert f.standard_label == "Investment Owned, at Fair Value" and f.documentation_label == "Fair value of investment owned."
    assert "{http://fasb.org/us-gaap/2024}InvestmentIdentifierAxis" in f.dimensions
    assert f.dimensions["{http://fasb.org/us-gaap/2024}InvestmentIdentifierAxis"].startswith("typed:Software Redwood Runway Bidco, LLC")
    assert f.dimension_labels["{http://synthetic.test/20250630}IndustryAxis"] == "Software [Member]"
    assert inventory.axes["{http://fasb.org/us-gaap/2024}InvestmentIdentifierAxis"]["typed"] is True
    dates = next(x for x in inventory.facts if x.fact_id == "h1m")
    assert dates.raw_value == "2031-12-17" and dates.numeric_value is None
    assert "http://synthetic.test/20250630" in inventory.extension_namespaces


def test_extensible_enumeration_values_resolve_to_member_labels():
    from bdc_soi.xbrl_inventory import resolve_enumeration_labels

    class _Concept:
        def __init__(self, label):
            self._l = label
            self.qname = "x:Y"

        def label(self, preferredLabel=None, lang=None, fallbackToQname=True):
            return self._l

    class _Model:
        qnameConcepts = {}

        def __init__(self):
            from arelle.ModelValue import QName

            self.qnameConcepts = {QName(None, "http://acme.test/2026", "MidwestEyeServicesMember"): _Concept("Midwest Eye Services [Member]")}

    m = _Model()
    assert resolve_enumeration_labels(m, "http://acme.test/2026#MidwestEyeServicesMember") == "Midwest Eye Services"
    assert resolve_enumeration_labels(m, "http://fasb.org/us-gaap/2026#SeniorLoansMember") == "Senior Loans"  # no label -> split camel case
    assert resolve_enumeration_labels(m, "not an enum") is None
