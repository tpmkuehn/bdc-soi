"""Concept-to-canonical-field mapping with explicit precedence (SPEC 11.3).

Tiers (recorded in ``mapping_rule``):
  1 ``template_exact``  - company template Clark or prefixed QName
  1b ``template_local`` - company template bare local-name fallback
  2 ``template_regex``  - company template regex over the Clark QName, label, documentation
  3 ``generic_exact``   - generic template Clark/prefixed QName
  3b ``generic_local``  - generic bare local name
  4 ``generic_regex``   - generic regex over QName, label and documentation
  5 unmapped
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bdc_soi.templates import ConceptRef, XbrlSpec, parse_concept_ref


@dataclass
class _ExactRule:
    field: str
    ref: ConceptRef
    tier: str
    position: int


@dataclass
class _RegexRule:
    field: str
    pattern: re.Pattern[str]
    tier: str
    position: int


@dataclass
class MappingResult:
    field: str | None
    rule: str | None
    tier: str | None


@dataclass
class ConceptMapper:
    families: dict[str, re.Pattern[str]]
    exact_rules: list[_ExactRule] = field(default_factory=list)
    regex_rules: list[_RegexRule] = field(default_factory=list)
    _cache: dict[str, MappingResult] = field(default_factory=dict)

    @classmethod
    def build(cls, company: XbrlSpec | None, generic: XbrlSpec | None, families: dict[str, re.Pattern[str]], extension_namespaces: list[str]) -> "ConceptMapper":
        fams = dict(families)
        if extension_namespaces:
            fams["issuer"] = re.compile("^(" + "|".join(re.escape(ns) for ns in extension_namespaces) + ")$")
        mapper = cls(families=fams)
        pos = 0
        for spec, tier_prefix in ((company, "template"), (generic, "generic")):
            if spec is None:
                continue
            for fld, refs in spec.field_concepts.items():
                for ref in refs:
                    cref = parse_concept_ref(ref)
                    tier = f"{tier_prefix}_local" if cref.kind == "local" else f"{tier_prefix}_exact"
                    mapper.exact_rules.append(_ExactRule(fld, cref, tier, pos))
                    pos += 1
            for fld, pats in spec.field_regex.items():
                for pat in pats:
                    mapper.regex_rules.append(_RegexRule(fld, re.compile(pat, re.IGNORECASE), f"{tier_prefix}_regex", pos))
                    pos += 1
        return mapper

    def map_concept(self, clark: str, namespace: str, local: str, label: str | None, documentation: str | None) -> MappingResult:
        key = clark
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        order = ("template_exact", "template_local", "template_regex", "generic_exact", "generic_local", "generic_regex")
        result = MappingResult(None, None, None)
        for tier in order:
            if tier.endswith("_regex"):
                for rule in self.regex_rules:
                    if rule.tier != tier:
                        continue
                    for text in (clark, label or "", documentation or ""):
                        if text and rule.pattern.search(text):
                            result = MappingResult(rule.field, f"{tier}:{rule.pattern.pattern}", tier)
                            break
                    if result.field:
                        break
            else:
                for rule in self.exact_rules:
                    if rule.tier == tier and rule.ref.matches(clark, namespace, local, self.families):
                        result = MappingResult(rule.field, f"{tier}:{rule.ref.raw}", tier)
                        break
            if result.field:
                break
        self._cache[key] = result
        return result

    def preference_rank(self, field_name: str, namespace: str, local: str, spec: XbrlSpec | None) -> int:
        """Rank for field_preference (lower is better); large when not listed."""
        if spec is None:
            return 999
        prefs = spec.field_preference.get(field_name) or []
        for i, item in enumerate(prefs):
            fam = self.families.get(item.namespace)
            ns_ok = bool(fam and fam.search(namespace)) or item.namespace == namespace
            if ns_ok and item.concept == local:
                return i
        return 999


def extract_qname_parts(clark: str) -> tuple[str, str]:
    """Split ``{namespace}local`` into (namespace, local)."""
    m = re.match(r"^\{([^}]*)\}(.+)$", clark)
    if not m:
        return "", clark
    return m.group(1), m.group(2)
