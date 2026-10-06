"""SOI presentation-role discovery (SPEC 11.4)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

DEFAULT_ROLE_PATTERNS = [
    r"Schedule\s+of\s+Investments",
    r"Consolidated\s+Schedule\s+of\s+Investments",
    r"Investment\s+Portfolio",
    r"Investments\s+Schedule",
    r"ScheduleOfInvestments",
]


@dataclass
class RoleRecord:
    uri: str
    definition: str | None
    is_candidate: bool
    matched_pattern: str | None
    concept_count: int
    concepts: list[str] = field(default_factory=list)
    axes: list[str] = field(default_factory=list)


@dataclass
class RoleDiscovery:
    roles: list[RoleRecord]
    soi_concepts: dict[str, list[str]]  # concept clark -> candidate role URIs
    soi_axes: set[str]


def discover_roles(model: Any, role_regex: list[str] | None = None) -> RoleDiscovery:
    from arelle import XbrlConst

    patterns = [re.compile(p, re.IGNORECASE) for p in (role_regex or []) + DEFAULT_ROLE_PATTERNS]
    pres = model.relationshipSet(XbrlConst.parentChild)
    roles: list[RoleRecord] = []
    soi_concepts: dict[str, list[str]] = {}
    soi_axes: set[str] = set()
    for uri in sorted(pres.linkRoleUris):
        definition = None
        rts = model.roleTypes.get(uri) or []
        if rts:
            definition = rts[0].definition
        matched = None
        for pat in patterns:
            if pat.search(uri) or (definition and pat.search(definition)):
                matched = pat.pattern
                break
        rel_set = model.relationshipSet(XbrlConst.parentChild, uri)
        concepts: set[str] = set()
        axes: set[str] = set()
        for rel in rel_set.modelRelationships:
            for obj in (rel.fromModelObject, rel.toModelObject):
                if obj is None or getattr(obj, "qname", None) is None:
                    continue
                clark = obj.qname.clarkNotation
                concepts.add(clark)
                if getattr(obj, "isDimensionItem", False):
                    axes.add(clark)
        rec = RoleRecord(uri, definition, matched is not None, matched, len(concepts), sorted(concepts), sorted(axes))
        roles.append(rec)
        if rec.is_candidate:
            for c in rec.concepts:
                soi_concepts.setdefault(c, []).append(uri)
            soi_axes |= axes
    return RoleDiscovery(roles, soi_concepts, soi_axes)
