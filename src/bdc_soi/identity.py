"""Deterministic holding identity and conservative deduplication (SPEC 15)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from bdc_soi.models import Holding
from bdc_soi.normalization import text_key


def holding_id(cik: str, accession: str, member_key: str | None = None, table_row: str | None = None) -> str:
    """SHA-256 of CIK, accession and the holding-axis member key (or table/row identity)."""
    if member_key:
        ident = f"member:{member_key}"
    elif table_row:
        ident = f"row:{table_row}"
    else:
        raise ValueError("holding identity requires a member key or table/row identity")
    digest = hashlib.sha256(f"{cik}|{accession}|{ident}".encode("utf-8")).hexdigest()
    return digest[:32]


def assign_ids(holdings: list[Holding]) -> None:
    for h in holdings:
        h.holding_id = holding_id(h.cik, h.accession_number, h.holding_member_key, h.html_row_id)


def strong_key(h: Holding) -> tuple:
    return (
        text_key(h.issuer),
        text_key(h.description),
        h.maturity_date.isoformat() if h.maturity_date else None,
        None if h.principal_amount is None else round(h.principal_amount, 2),
        None if h.cost is None else round(h.cost, 2),
        None if h.amortized_cost is None else round(h.amortized_cost, 2),
        None if h.fair_value is None else round(h.fair_value, 2),
        None if h.spread_bps is None else round(h.spread_bps, 2),
        h.reference_index,
    )


@dataclass
class DedupResult:
    kept: list[Holding]
    removed: list[Holding]
    notes: list[str] = field(default_factory=list)


def deduplicate(holdings: list[Holding]) -> DedupResult:
    """Collapse only identical source identities; flag (never merge) strong-field duplicates.

    Two instruments that share issuer and monetary values are legitimately distinct unless
    description, rate, maturity and source identity also agree, so strong-field duplicates
    across different source identities are only queued for review.
    """
    seen: dict[str, Holding] = {}
    removed: list[Holding] = []
    notes: list[str] = []
    for h in holdings:
        if h.holding_id in seen:
            removed.append(h)
            seen[h.holding_id].add_flag("duplicate_source_identity_merged")
            notes.append(f"duplicate_holding_id:{h.holding_id}")
            continue
        seen[h.holding_id] = h
    kept = list(seen.values())
    groups: dict[tuple, list[Holding]] = {}
    for h in kept:
        k = strong_key(h)
        if k[0] or k[1]:
            groups.setdefault(k, []).append(h)
    for k, members in groups.items():
        if len(members) > 1:
            for h in members:
                h.add_flag("possible_duplicate_strong_fields")
    return DedupResult(kept, removed, notes)
