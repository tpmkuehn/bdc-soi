import re

import pytest

from bdc_soi.concept_mapping import ConceptMapper, extract_qname_parts
from bdc_soi.templates import XbrlSpec, parse_concept_ref

FAM = {"us-gaap": re.compile(r"^http://fasb\.org/us-gaap/\d{4}$")}


def test_qname_extraction():
    assert extract_qname_parts("{http://fasb.org/us-gaap/2025}InvestmentOwnedAtCost") == ("http://fasb.org/us-gaap/2025", "InvestmentOwnedAtCost")
    assert parse_concept_ref("{http://x}Local").kind == "clark"
    assert parse_concept_ref("us-gaap:InvestmentOwnedAtCost").kind == "prefixed"
    assert parse_concept_ref("PortfolioCompanyName").kind == "local"
    with pytest.raises(ValueError):
        parse_concept_ref("{issuer-namespace}InvestmentIdentifierAxis")
    with pytest.raises(ValueError):
        parse_concept_ref("bad name!")


def test_mapping_precedence():
    company = XbrlSpec(field_concepts={"fair_value": ["{http://acme.test/2025}FV"], "cost": ["AcmeCost"]}, field_regex={"principal_amount": ["Principal"]})
    generic = XbrlSpec(field_concepts={"fair_value": ["us-gaap:InvestmentOwnedAtFairValue"], "amortized_cost": ["us-gaap:InvestmentOwnedAtAmortizedCost"], "cost": ["us-gaap:InvestmentOwnedAtCost"]}, field_regex={"amortized_cost": ["AmortizedCost"], "cost": ["AtCost$"]})
    m = ConceptMapper.build(company, generic, FAM, ["http://acme.test/2025"])
    assert m.map_concept("{http://acme.test/2025}FV", "http://acme.test/2025", "FV", None, None).tier == "template_exact"
    assert m.map_concept("{http://acme.test/2025}AcmeCost", "http://acme.test/2025", "AcmeCost", None, None).tier == "template_local"
    assert m.map_concept("{http://acme.test/2025}LoanPrincipal", "http://acme.test/2025", "LoanPrincipal", None, None).tier == "template_regex"
    r = m.map_concept("{http://fasb.org/us-gaap/2025}InvestmentOwnedAtFairValue", "http://fasb.org/us-gaap/2025", "InvestmentOwnedAtFairValue", "Investment Owned, at Fair Value", None)
    assert (r.field, r.tier) == ("fair_value", "generic_exact")
    # Specific (amortized cost) must win over broad cost in the regex tier.
    r2 = m.map_concept("{http://acme.test/2025}InvestmentOwnedAtAmortizedCost", "http://acme.test/2025", "InvestmentOwnedAtAmortizedCost", None, None)
    assert (r2.field, r2.tier) == ("amortized_cost", "generic_regex")
    assert m.map_concept("{http://acme.test/2025}Unrelated", "http://acme.test/2025", "Unrelated", "Nothing", None).field is None
    # Exact prefixed refs do not match a different namespace family.
    assert m.map_concept("{http://other.test}InvestmentOwnedAtFairValue", "http://other.test", "InvestmentOwnedAtFairValue", None, None).tier != "generic_exact"


def test_issuer_family_resolves_to_extension_namespace():
    company = XbrlSpec(field_concepts={"fair_value": ["issuer:FV"]})
    m = ConceptMapper.build(company, None, FAM, ["http://acme.test/2025"])
    assert m.map_concept("{http://acme.test/2025}FV", "http://acme.test/2025", "FV", None, None).tier == "template_exact"
    assert m.map_concept("{http://fasb.org/us-gaap/2025}FV", "http://fasb.org/us-gaap/2025", "FV", None, None).field is None
