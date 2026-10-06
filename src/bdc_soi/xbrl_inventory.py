"""Complete fact inventory with semantic dates and dimension serialization (SPEC 11.1, 11.2)."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from bdc_soi.models import FactRecord

DEI_DOC_PERIOD_END = "DocumentPeriodEndDate"


# ---------------------------------------------------------------------------
# Semantic dates (11.2)
# ---------------------------------------------------------------------------


def semantic_instant_date(dt: datetime | date | None) -> date | None:
    """Arelle stores a date-only instant as midnight of the *following* day; map it back."""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.time() == time(0, 0):
            return (dt - timedelta(days=1)).date()
        return dt.date()
    return dt


def semantic_end_date(dt: datetime | date | None) -> date | None:
    return semantic_instant_date(dt)


def semantic_start_date(dt: datetime | date | None) -> date | None:
    if dt is None:
        return None
    return dt.date() if isinstance(dt, datetime) else dt


def semantic_period(context: Any) -> tuple[str, date | None, date | None]:
    """Return (period_type, start, end) with semantic reporting dates."""
    if context.isInstantPeriod:
        end = semantic_instant_date(context.instantDatetime)
        return "instant", None, end
    if context.isStartEndPeriod:
        return "duration", semantic_start_date(context.startDatetime), semantic_end_date(context.endDatetime)
    return "forever", None, None


# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------


def dimension_signature(dims: dict[str, str]) -> str:
    """Deterministic, complete serialization of a context's dimensions."""
    return "|".join(f"{axis}={member}" for axis, member in sorted(dims.items()))


def _concept_label(concept: Any, role: str | None = None) -> str | None:
    try:
        label = concept.label(preferredLabel=role, lang="en", fallbackToQname=False)
    except TypeError:
        label = concept.label(preferredLabel=role, lang="en")
    if not label or label == str(concept.qname):
        return None
    return str(label)


def decode_label(text: str) -> str:
    """Typed-member values and labels may carry literal HTML entities ('&amp;'); decode them once."""
    return html.unescape(str(text)) if text else str(text or "")


def context_dimensions(context: Any) -> tuple[dict[str, str], dict[str, str]]:
    dims: dict[str, str] = {}
    labels: dict[str, str] = {}
    for dim_qname, dim_value in context.qnameDims.items():
        axis = dim_qname.clarkNotation
        if dim_value.isTyped:
            typed = dim_value.typedMember
            text = decode_label(typed.stringValue if typed is not None else "")
            dims[axis] = f"typed:{text}"
            labels[axis] = str(text)
        else:
            member_q = dim_value.memberQname
            dims[axis] = member_q.clarkNotation if member_q is not None else ""
            member = dim_value.member
            lbl = _concept_label(member) if member is not None else None
            labels[axis] = decode_label(lbl or (str(member_q) if member_q is not None else ""))
    return dims, labels


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


@dataclass
class Inventory:
    facts: list[FactRecord]
    report_date: date | None
    report_date_source: str
    document_type: str
    extension_namespaces: list[str]
    contexts: dict[str, dict[str, Any]]
    axes: dict[str, dict[str, Any]]  # axis clark -> {"typed": bool, "label": str}


def _unit_string(fact: Any) -> str | None:
    unit = getattr(fact, "unit", None)
    if unit is None:
        return None
    try:
        mul, div = unit.measures
        num = "*".join(str(m.localName) for m in mul)
        den = "*".join(str(m.localName) for m in div)
        return f"{num}/{den}" if den else num
    except Exception:  # pragma: no cover - defensive
        return str(unit.value)


def _numeric(fact: Any) -> float | None:
    if fact.isNil or not getattr(fact.concept, "isNumeric", False):
        return None
    try:
        xv = fact.xValue
    except Exception:
        xv = None
    if xv is None:
        try:
            return float(str(fact.value).replace(",", ""))
        except (TypeError, ValueError):
            return None
    try:
        return float(xv)
    except (TypeError, ValueError):
        return None


_ENUM_VALUE_RE = re.compile(r"^(?P<ns>\S+?)#(?P<local>[^\s#]+)$")


def resolve_enumeration_labels(model: Any, raw: str) -> str | None:
    """Map an extensible-enumeration value (``namespace#LocalMember``, space-separated for sets) to member labels."""
    labels: list[str] = []
    for token in str(raw).split():
        m = _ENUM_VALUE_RE.match(token)
        if not m:
            return None
        try:
            from arelle.ModelValue import QName

            concept = model.qnameConcepts.get(QName(None, m.group("ns"), m.group("local")))
        except Exception:  # pragma: no cover - defensive
            concept = None
        label = _concept_label(concept) if concept is not None else None
        if not label:
            label = re.sub(r"(?<!^)(?=[A-Z])", " ", re.sub(r"Member$", "", m.group("local"))).strip()
        labels.append(re.sub(r"\s*\[Member\]\s*$", "", label))
    return "; ".join(labels) if labels else None


def build_inventory(model: Any, document_type: str, extension_namespaces: list[str], fallback_report_date: date | None = None) -> Inventory:
    facts_out: list[FactRecord] = []
    contexts: dict[str, dict[str, Any]] = {}
    axes: dict[str, dict[str, Any]] = {}
    dei_period_end: date | None = None

    ordered = sorted(model.facts, key=lambda f: f.objectIndex)
    for idx, fact in enumerate(ordered):
        ctx = fact.context
        if ctx is None or fact.concept is None:
            continue
        period_type, start, end = semantic_period(ctx)
        if ctx.id not in contexts:
            dims, labels = context_dimensions(ctx)
            contexts[ctx.id] = {"period_type": period_type, "start": start, "end": end, "dims": dims, "labels": labels, "signature": dimension_signature(dims)}
            for dim_qname, dim_value in ctx.qnameDims.items():
                axis = dim_qname.clarkNotation
                if axis not in axes:
                    axes[axis] = {"typed": bool(dim_value.isTyped), "label": _concept_label(dim_value.dimension) or str(dim_qname)}
        cinfo = contexts[ctx.id]
        concept = fact.concept
        qn = fact.qname
        raw = None if fact.isNil else (str(fact.value) if fact.value is not None else None)
        try:
            xval = None if fact.isNil else fact.xValue
        except Exception:
            xval = None
        data_type = str(concept.baseXbrliType) if getattr(concept, "baseXbrliType", None) else None
        type_name = str(getattr(concept, "typeQname", "") or "")
        if raw and ("enumeration" in (data_type or "").lower() or "enumeration" in type_name.lower()) and "#" in raw:
            resolved = resolve_enumeration_labels(model, raw)
            if resolved:
                xval = resolved
        rec = FactRecord(
            fact_id=fact.id or f"fact-{idx}",
            concept_clark=qn.clarkNotation,
            concept_prefixed=str(qn),
            local_name=qn.localName,
            namespace=qn.namespaceURI,
            standard_label=_concept_label(concept),
            documentation_label=_concept_label(concept, "http://www.xbrl.org/2003/role/documentation"),
            raw_value=raw,
            normalized_value=xval if isinstance(xval, (str, int, float, bool)) else (str(xval) if xval is not None else None),
            numeric_value=_numeric(fact),
            is_nil=bool(fact.isNil),
            unit=_unit_string(fact),
            decimals=str(fact.decimals) if fact.decimals is not None else None,
            context_id=ctx.id,
            period_type=period_type,
            period_start=start,
            period_end=end,
            dimensions=dict(cinfo["dims"]),
            dimension_labels=dict(cinfo["labels"]),
            dimension_signature=cinfo["signature"],
            data_type=data_type,
            order_index=idx,
        )
        facts_out.append(rec)
        if qn.localName == DEI_DOC_PERIOD_END and not rec.dimensions and not fact.isNil:
            try:
                dei_period_end = datetime.strptime(str(fact.value).strip()[:10], "%Y-%m-%d").date()
            except ValueError:
                dei_period_end = None

    if dei_period_end is not None:
        report_date, source = dei_period_end, "dei:DocumentPeriodEndDate"
    elif fallback_report_date is not None:
        report_date, source = fallback_report_date, "submissions_metadata"
    else:
        # Most common instant end date among non-dimensional facts.
        counts: dict[date, int] = {}
        for f in facts_out:
            if f.period_type == "instant" and f.period_end and not f.dimensions:
                counts[f.period_end] = counts.get(f.period_end, 0) + 1
        report_date = max(sorted(counts), key=lambda d: counts[d]) if counts else None
        source = "most_common_instant" if report_date else "unknown"
    return Inventory(facts_out, report_date, source, document_type, extension_namespaces, contexts, axes)
