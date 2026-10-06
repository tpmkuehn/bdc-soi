"""XBRL holding construction: grouping, duplicate selection, conflicts, totals (SPEC 11.6, 11.7, 16.1)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from bdc_soi.concept_mapping import ConceptMapper, extract_qname_parts
from bdc_soi.models import DATE_FIELDS, MONETARY_FIELDS, NUMERIC_FIELDS, RATE_FIELDS, FactRecord, FieldConflict, Holding
from bdc_soi.normalization import coerce_value, normalize_issuer
from bdc_soi.templates import LegalSuffixes, XbrlSpec, parse_concept_ref

GENERIC_DIMENSION_FIELDS = [
    (re.compile(r"IssuerName|PortfolioCompanyName|InvestmentIssuer(?!Affiliation)", re.IGNORECASE), "issuer"),
    (re.compile(r"Industry|Sector", re.IGNORECASE), "industry"),
    (re.compile(r"Geograph|Country|Region", re.IGNORECASE), "country"),
    (re.compile(r"InvestmentType|TypeOfInvestment|InvestmentsByType|SecurityType", re.IGNORECASE), "investment_type"),
    (re.compile(r"Affiliat", re.IGNORECASE), "affiliate_status"),
    (re.compile(r"Currency", re.IGNORECASE), "currency"),
]
TOTAL_FIELDS = ("fair_value", "cost", "amortized_cost")
# Exact total / net-asset phrasings only: an issuer such as 'Total Expert Inc. | Growth Capital Loan' is a holding.
NON_HOLDING_MEMBER_RE = re.compile(r"^(?:Total(?:\s+(?:Portfolio\s+)?Investments?)?(?:\s+(?:at|in)\s+Fair\s+Value)?(?:,\s*.*)?|Net\s+Assets(?:\s*\(.*\))?|Liabilities\s+in\s+Excess\s+of\s+Other\s+Assets.*|Other\s+Assets\s+in\s+Excess.*|Investments)$", re.IGNORECASE)
SUBSIDIARY_AXIS_RE = re.compile(r"ConsolidatedSubsidiar|ConsolidatedEntit|LegalEntityAxis|SubsidiaryAxis", re.IGNORECASE)
REFERENCE_INDEX_ENUM_ALIASES = [
    (re.compile(r"SecuredOvernightFinancingRate|\bSOFR\b", re.IGNORECASE), "SOFR"),
    (re.compile(r"LondonInterbankOfferedRate|\bLIBOR\b", re.IGNORECASE), "LIBOR"),
    (re.compile(r"PrimeRate|\bPrime\b", re.IGNORECASE), "Prime"),
    (re.compile(r"EuroInterbankOfferedRate|\bEURIBOR\b", re.IGNORECASE), "EURIBOR"),
    (re.compile(r"SterlingOvernightIndexAverage|\bSONIA\b", re.IGNORECASE), "SONIA"),
    (re.compile(r"CanadianOvernightRepoRateAverage|\bCORRA\b", re.IGNORECASE), "CORRA"),
    (re.compile(r"CanadianDollarOfferedRate|\bCDOR\b", re.IGNORECASE), "CDOR"),
    (re.compile(r"BankBillSwapBid|\bBBSY\b|B\s?B\s?S\s?Y", re.IGNORECASE), "BBSY"),
    (re.compile(r"BankBillSwap|\bBBSW\b", re.IGNORECASE), "BBSW"),
    (re.compile(r"StockholmInterbank|\bSTIBOR\b", re.IGNORECASE), "STIBOR"),
    (re.compile(r"NorwegianInterbank|\bNIBOR\b", re.IGNORECASE), "NIBOR"),
    (re.compile(r"TokyoOvernightAverage|\bTONAR\b", re.IGNORECASE), "TONAR"),
    (re.compile(r"SingaporeOvernightRateAverage|\bSORA\b", re.IGNORECASE), "SORA"),
    (re.compile(r"BaseRate", re.IGNORECASE), "Base Rate"),
]


def normalize_reference_index_enum(raw: str) -> str:
    """Map an extensible-enumeration member QName/URI (e.g. ``...#SecuredOvernightFinancingRateSofrMember``) to a canonical index name."""
    token = raw.strip()
    token = token.split("#")[-1].split(":")[-1].split("}")[-1]
    token = re.sub(r"Member$", "", token)
    for pat, name in REFERENCE_INDEX_ENUM_ALIASES:
        if pat.search(token):
            return name
    return re.sub(r"(?<!^)(?=[A-Z])", " ", token).strip()
STANDARD_NS_RE = re.compile(r"^http://(fasb\.org|xbrl\.sec\.gov|www\.xbrl\.org|xbrl\.org)/")


@dataclass
class TotalCandidate:
    field: str
    value: float
    source: str  # xbrl_template_total | xbrl_no_dimensions | xbrl_classification_subtotal
    concept: str
    fact_id: str
    context_id: str
    dimension_signature: str
    unit: str | None
    rank: int

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


AFFILIATE_SCHEDULE_RE = re.compile(r"^InvestmentsInAndAdvancesToAffiliates|^GrossInvestmentIncome|^InterestAndDividendIncomeOperating$|^DebtAndEquitySecuritiesRealizedGainLoss$|^DebtAndEquitySecuritiesUnrealizedGainLoss$|^DerivativeAndForeignCurrencyTransactionPriceChange")
SOI_SPECIFIC_FIELDS = {"principal_amount", "face_amount", "shares", "spread", "maturity_date", "interest_rate", "rate_floor", "pik_rate", "cash_rate", "reference_index"}


@dataclass
class ExcludedCandidate:
    """A holding-axis member that is not exported as a canonical holding, with the rule and evidence."""

    member_key: str
    label: str
    rule: str
    evidence: str
    fair_value: float | None = None
    cost: float | None = None
    fact_ids: list[str] = field(default_factory=list)
    context_ids: list[str] = field(default_factory=list)

    def to_row(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["fact_ids"] = ";".join(self.fact_ids)
        d["context_ids"] = ";".join(sorted(set(self.context_ids)))
        return d


@dataclass
class XbrlExtraction:
    holdings: list[Holding]
    totals: list[TotalCandidate]
    group_count: int
    notes: list[str] = field(default_factory=list)
    excluded: list[ExcludedCandidate] = field(default_factory=list)


def _member_label_text(dim_value: str, label: str) -> str:
    if dim_value.startswith("typed:"):
        return dim_value[len("typed:") :]
    return label


def _expected_unit_ok(fld: str, unit: str | None) -> bool:
    if fld in MONETARY_FIELDS:
        return unit is not None and re.fullmatch(r"[A-Z]{3}", unit) is not None
    if fld in RATE_FIELDS or fld == "percent_of_net_assets":
        return unit in (None, "pure", "percent") or (unit or "").lower() in {"pure", "percent"}
    if fld == "shares":
        return unit in (None, "shares", "pure") or "shares" in (unit or "").lower()
    return True


def rank_fact(fact: FactRecord, fld: str, mapper: ConceptMapper, spec: XbrlSpec | None, report_date: date | None, selected_axis: str) -> tuple:
    """Deterministic ranking key (lower is better) per SPEC 11.7."""
    ns, local = extract_qname_parts(fact.concept_clark)
    pref = mapper.preference_rank(fld, ns, local, spec)
    tier_rank = {"template_exact": 0, "template_local": 1, "template_regex": 2, "generic_exact": 3, "generic_local": 4, "generic_regex": 5}.get(fact.mapping_rule.split(":")[0] if fact.mapping_rule else "", 6)
    in_role = 0 if fact.in_soi_role else 1
    nil = 1 if fact.is_nil else 0
    unit_ok = 0 if _expected_unit_ok(fld, fact.unit) else 1
    period_ok = 0 if (report_date is None or fact.period_end == report_date) else 1
    taxonomy = 0 if STANDARD_NS_RE.match(ns) else 1
    try:
        decimals = -int(fact.decimals) if fact.decimals not in (None, "INF") else (-99 if fact.decimals == "INF" else 0)
    except ValueError:
        decimals = 0
    extra_dims = len([a for a in fact.dimensions if a != selected_axis])
    return (pref, tier_rank, in_role, nil, unit_ok, period_ok, taxonomy, decimals, extra_dims, fact.order_index, fact.fact_id)


def _materially_different(fld: str, a: Any, b: Any) -> bool:
    if b is None:
        return False  # a nil/absent alternative is not a competing value
    if a is None:
        return True
    if fld in NUMERIC_FIELDS:
        try:
            fa, fb = float(a), float(b)
        except (TypeError, ValueError):
            return str(a) != str(b)
        tol = max(1.0 if fld in MONETARY_FIELDS else 1e-6, abs(fa) * 1e-4)
        return abs(fa - fb) > tol
    return str(a).strip() != str(b).strip()


def _fact_value(fact: FactRecord, fld: str, date_formats: list[str]) -> tuple[Any, str | None]:
    if fact.is_nil:
        return None, "nil"
    if fld in {"issuer", "description", "industry", "sector", "country", "investment_type", "affiliate_status", "controlled_status"} and isinstance(fact.normalized_value, str) and fact.raw_value and "#" in fact.raw_value and fact.normalized_value != fact.raw_value:
        return fact.normalized_value, "enumeration_label"
    if fld in NUMERIC_FIELDS and fact.numeric_value is not None:
        return fact.numeric_value, None
    if fld in DATE_FIELDS:
        return coerce_value(fld, fact.raw_value, date_formats)
    if fld in NUMERIC_FIELDS:
        return coerce_value(fld, fact.raw_value, date_formats)
    return coerce_value(fld, fact.raw_value, date_formats)


def _group_sum(facts: list[FactRecord], fld: str) -> float | None:
    vals = [f.numeric_value for f in facts if f.mapped_field == fld and f.numeric_value is not None and not f.is_nil]
    return max(vals, key=abs) if vals else None


def _parent_members(groups: dict[str, list[FactRecord]], axis: str) -> set[str]:
    """Typed members whose label is a prefix of other members' labels AND whose fair value (or cost) equals the
    sum of those members are section nodes (e.g. 'Investment in non-controlled, Affiliated Investments'), not holdings."""
    labels = {m: _member_label_text(m, fs[0].dimension_labels.get(axis, m)).strip() for m, fs in groups.items()}
    parents: set[str] = set()
    for m, label in labels.items():
        if len(label) < 3:
            continue
        children = [c for c, cl in labels.items() if c != m and cl.startswith(label) and len(cl) > len(label) and cl[len(label)] in " ,|-–:;/("]
        if len(children) < 2:
            continue  # a single prefixed sibling (e.g. 'X | Term Loan' vs 'X | Term Loan | Funded') is a distinct facility, not a parent
        for fld in ("fair_value", "cost", "amortized_cost"):
            pv = _group_sum(groups[m], fld)
            if pv is None:
                continue
            cs = [_group_sum(groups[c], fld) for c in children]
            cs = [v for v in cs if v is not None]
            if cs and abs(sum(cs) - pv) <= max(1.0, abs(pv) * 1e-4):
                parents.add(m)
                break
    return parents


def _dimension_field_rules(spec: XbrlSpec | None, families: dict[str, re.Pattern[str]]) -> list[tuple[Any, str, str]]:
    rules: list[tuple[Any, str, str]] = []
    if spec:
        for axis_ref, fld in spec.dimension_fields.items():
            rules.append((parse_concept_ref(axis_ref), fld, f"template_dimension_field:{axis_ref}"))
    return rules


def build_xbrl_holdings(
    facts: list[FactRecord],
    report_date: date | None,
    selected_axis: str | None,
    mapper: ConceptMapper,
    spec: XbrlSpec | None,
    generic_spec: XbrlSpec | None,
    families: dict[str, re.Pattern[str]],
    base: dict[str, Any],
    legal_suffixes: LegalSuffixes | None = None,
    date_formats: list[str] | None = None,
    instance_document: str | None = None,
) -> XbrlExtraction:
    date_formats = date_formats or ["%Y-%m-%d", "%m/%d/%Y"]
    ctx_filters = (spec or generic_spec).context_filters if (spec or generic_spec) else None
    allowed_period_types = set(ctx_filters.allowed_period_types) if ctx_filters else {"instant"}
    require_report_date = ctx_filters.require_report_date if ctx_filters else True
    excluded_axes = [re.compile(p, re.IGNORECASE) for p in (ctx_filters.excluded_axes_regex if ctx_filters else [])]
    notes: list[str] = []

    # ---- totals: mapped total fields at report date without the holding axis (16.1 sources 1-2)
    totals: list[TotalCandidate] = []
    template_total_refs = {fld: [parse_concept_ref(r) for r in refs] for fld, refs in ((spec.total_concepts if spec else {}) or {}).items()}
    for f in facts:
        if f.is_nil or f.numeric_value is None:
            continue
        if report_date is not None and f.period_end != report_date:
            continue
        if selected_axis and selected_axis in f.dimensions:
            continue
        ns, local = extract_qname_parts(f.concept_clark)
        tmpl_field = None
        if not f.dimensions:  # a template total concept identifies the undimensioned (entity-wide) fact
            for fld, refs in template_total_refs.items():
                if any(r.matches(f.concept_clark, ns, local, mapper.families) for r in refs):
                    tmpl_field = fld
        fld = tmpl_field or (f.mapped_field if f.mapped_field in TOTAL_FIELDS else None)
        if fld is None:
            continue
        if tmpl_field:
            source, rank = "xbrl_template_total", 0
        elif not f.dimensions:
            source, rank = "xbrl_no_dimensions", 1
        else:
            source, rank = "xbrl_classification_subtotal", 4
        totals.append(TotalCandidate(fld, f.numeric_value, source, f.concept_clark, f.fact_id, f.context_id, f.dimension_signature, f.unit, rank))
    totals.sort(key=lambda t: (t.field, t.rank, t.dimension_signature, t.fact_id))

    if not selected_axis:
        return XbrlExtraction([], totals, 0, ["no_holding_axis_selected"])

    # ---- group facts by holding member
    groups: dict[str, list[FactRecord]] = {}
    member_concepts: dict[str, set[str]] = {}  # every concept tagged on the member, any period (schedule evidence)
    for f in facts:
        member = f.dimensions.get(selected_axis)
        if member is None:
            continue
        member_concepts.setdefault(member, set()).add(f.local_name)
        if f.period_type not in allowed_period_types:
            continue
        if require_report_date and report_date is not None and f.period_end != report_date:
            continue
        if any(p.search(extract_qname_parts(a)[1]) for a in f.dimensions for p in excluded_axes if a != selected_axis):
            continue
        groups.setdefault(member, []).append(f)

    dim_rules = _dimension_field_rules(spec, families)
    holdings: list[Holding] = []
    excluded: list[ExcludedCandidate] = []
    skipped_no_monetary = 0
    parents = _parent_members(groups, selected_axis)
    member_excl = [re.compile(p, re.IGNORECASE) for p in (spec.row_axes.exclude_member_regex if spec else [])]

    def _exclude(member: str, label: str, rule: str, evidence: str) -> None:
        gf = groups[member]
        excluded.append(ExcludedCandidate(member, label, rule, evidence, _group_sum(gf, "fair_value"), _group_sum(gf, "cost"), [f.fact_id for f in gf], [f.context_id for f in gf]))

    for member in sorted(groups):
        member_text0 = _member_label_text(member, groups[member][0].dimension_labels.get(selected_axis, member)).strip()
        gfacts0 = groups[member]
        if any(p.search(member_text0) for p in member_excl):
            notes.append(f"xbrl_member_excluded_by_template:{member_text0[:80]}")
            _exclude(member, member_text0, "template:row_axes.exclude_member_regex", (spec.row_axes.exclude_member_evidence if spec else None) or "")
            continue
        if NON_HOLDING_MEMBER_RE.match(member_text0):
            # A total / net-assets line tagged as an axis member (observed: PIMCO 'Total Investments', Muzinich 'Net Assets').
            for f in gfacts0:
                if f.mapped_field in TOTAL_FIELDS and f.numeric_value is not None and not f.is_nil:
                    totals.append(TotalCandidate(f.mapped_field, f.numeric_value, "xbrl_member_total", f.concept_clark, f.fact_id, f.context_id, f.dimension_signature, f.unit, 1 if member_text0.lower().startswith("total investments") else 6))
            notes.append(f"xbrl_non_holding_member_excluded:{member_text0[:60]}")
            _exclude(member, member_text0, "generic:non_holding_member_label", "member label is an exact total/net-assets phrasing; its facts are kept as reported-total candidates")
            continue
        if member in parents:
            notes.append(f"xbrl_parent_member_excluded:{member_text0[:80]}")
            _exclude(member, member_text0, "generic:parent_member_sum_of_children", "label is a prefix of >=2 other members and its value equals their sum")
            continue
        concepts = member_concepts.get(member, set())
        mapped = {f.mapped_field for f in gfacts0 if f.mapped_field}
        if any(AFFILIATE_SCHEDULE_RE.match(c) for c in concepts) and not (mapped & SOI_SPECIFIC_FIELDS):
            # Investments-in-affiliates schedule (roll-forward concepts, no principal/rate/maturity facts): a separate
            # schedule, not an SOI row (observed: Chicago Atlantic 'CO Acquisition Vehicle LLC', Golub one-part members).
            notes.append(f"xbrl_affiliate_schedule_member_excluded:{member_text0[:60]}")
            _exclude(member, member_text0, "generic:affiliate_schedule_member", "facts are investments-in-affiliates roll-forward concepts (" + ", ".join(sorted(c for c in concepts if AFFILIATE_SCHEDULE_RE.match(c)))[:160] + ") with no SOI-specific facts")
            continue
        gfacts = sorted(groups[member], key=lambda x: (x.order_index, x.fact_id))
        h = Holding(**base)
        h.source_method = "xbrl"
        h.source_document = instance_document
        h.holding_member_key = member
        axis_label = gfacts[0].dimension_labels.get(selected_axis, member)
        member_text = _member_label_text(member, axis_label)
        h.member_labels = {selected_axis: member_text}
        # Preserve the union of complete context dimensions as lineage.
        signatures = sorted({f.dimension_signature for f in gfacts})
        h.dimension_signature = signatures[0] if len(signatures) == 1 else " || ".join(signatures)
        h.source_context_ids = sorted({f.context_id for f in gfacts})
        h.source_fact_ids = [f.fact_id for f in gfacts]

        # Field candidates with deterministic ranking.
        by_field: dict[str, list[FactRecord]] = {}
        for f in gfacts:
            if f.mapped_field and f.mapped_field in NUMERIC_FIELDS | set(DATE_FIELDS) | {"issuer", "description", "industry", "sector", "country", "investment_type", "reference_index", "currency", "affiliate_status", "controlled_status", "non_accrual_flag", "footnote_markers", "interest_rate_text"}:
                by_field.setdefault(f.mapped_field, []).append(f)
        for fld in sorted(by_field):
            cands = sorted(by_field[fld], key=lambda x: rank_fact(x, fld, mapper, spec, report_date, selected_axis))
            best = cands[0]
            target = "interest_rate" if fld == "interest_rate_text" else fld
            value, diag = _fact_value(best, target, date_formats)
            if fld == "reference_index" and isinstance(value, str):
                value = normalize_reference_index_enum(best.raw_value or value)
            if fld == "issuer" and isinstance(value, str):
                h.issuer_name_raw = best.raw_value
                value = normalize_issuer(value, legal_suffixes)
            if fld == "description" and isinstance(value, str):
                h.description_raw = best.raw_value
            if target in {"spread", "spread_bps"} and isinstance(value, (int, float)):
                # XBRL spreads are decimal rates (pure); derive both representations.
                if target == "spread":
                    h.set_field("spread_bps", round(value * 10000.0, 6), source="xbrl_fact", raw_value=best.raw_value, source_ref=best.fact_id, rule_id=best.mapping_rule, transformation="decimal_to_bps")
                else:
                    h.set_field("spread", round(value / 10000.0, 10), source="xbrl_fact", raw_value=best.raw_value, source_ref=best.fact_id, rule_id=best.mapping_rule, transformation="bps_to_decimal")
            h.set_field(target, value, source="xbrl_fact", raw_value=best.raw_value, rule_id=best.mapping_rule, source_ref=best.fact_id, transformation=diag)
            h.source_concepts[target] = best.concept_clark
            if diag and target in DATE_FIELDS and value is None:
                h.add_flag(f"date_parse:{target}:{diag}")
            alternatives = []
            for alt in cands[1:]:
                alt_val, _ = _fact_value(alt, target, date_formats)
                if _materially_different(target, value, alt_val):
                    alternatives.append({"fact_id": alt.fact_id, "concept": alt.concept_clark, "context_id": alt.context_id, "value": alt_val if not isinstance(alt_val, date) else alt_val.isoformat(), "dimension_signature": alt.dimension_signature})
            if alternatives:
                h.field_conflicts.append(FieldConflict(field=target, selected=value if not isinstance(value, date) else value.isoformat(), alternatives=alternatives, reason="materially_different_duplicate_facts"))
                h.add_flag(f"field_conflict:{target}")

        # Classification dimensions -> fields (lineage preserved; never a separate holding).
        class_members: dict[str, dict[str, str]] = {}
        for f in gfacts:
            for axis, member_val in f.dimensions.items():
                if axis == selected_axis:
                    continue
                label = _member_label_text(member_val, f.dimension_labels.get(axis, member_val))
                class_members.setdefault(axis, {})[member_val] = label
        for axis in sorted(class_members):
            ns, local = extract_qname_parts(axis)
            target_field: str | None = None
            rule_id: str | None = None
            for cref, fld, rid in dim_rules:
                if cref.matches(axis, ns, local, mapper.families):
                    target_field, rule_id = fld, rid
                    break
            if target_field is None:
                for pat, fld in GENERIC_DIMENSION_FIELDS:
                    if pat.search(local):
                        target_field, rule_id = fld, f"generic_dimension_field:{pat.pattern}"
                        break
            members = class_members[axis]
            labels = sorted(set(members.values()))
            h.member_labels[axis] = "; ".join(labels)
            if target_field is None:
                continue
            if len(labels) > 1:
                h.field_conflicts.append(FieldConflict(field=target_field, selected=labels[0], alternatives=[{"axis": axis, "value": lbl} for lbl in labels[1:]], reason="multiple_members_on_classification_axis"))
                h.add_flag(f"field_conflict:{target_field}")
            clean = re.sub(r"\s*\[Member\]\s*$", "", labels[0]).strip()
            if getattr(h, target_field) is None:
                value_out: Any = clean
                if target_field == "issuer":
                    h.issuer_name_raw = clean
                    value_out = normalize_issuer(clean, legal_suffixes)
                h.set_field(target_field, value_out, source="xbrl_dimension_member", raw_value=labels[0], rule_id=rule_id, source_ref=axis)
                h.source_concepts[target_field] = axis
            if target_field == "affiliate_status" and h.controlled_status is None and re.search(r"control", clean, re.IGNORECASE):
                h.set_field("controlled_status", clean, source="xbrl_dimension_member", raw_value=labels[0], rule_id=rule_id, source_ref=axis)

        sub_axes = sorted({a for f in gfacts for a in f.dimensions if a != selected_axis and SUBSIDIARY_AXIS_RE.search(extract_qname_parts(a)[1])})
        if sub_axes:
            h.add_flag("xbrl_subsidiary_context:" + ";".join(extract_qname_parts(a)[1] for a in sub_axes))
        if all(getattr(h, fld) is None for fld in ("fair_value", "cost", "amortized_cost", "principal_amount", "face_amount", "shares")):
            skipped_no_monetary += 1  # e.g. unfunded-commitment members carrying only rate/maturity facts
            _exclude(member, member_text, "generic:no_monetary_values", "member carries no fair value, cost, amortized cost, principal, face or shares fact at the report date")
            continue
        # Member label as issuer source when no direct issuer concept is present.
        if h.issuer is None:
            h.issuer_name_raw = member_text
            h.set_field("issuer", normalize_issuer(member_text, legal_suffixes), source="xbrl_dimension_member", raw_value=member_text, source_ref=selected_axis, transformation="member_label")
            h.source_concepts["issuer"] = selected_axis
        elif h.issuer_name_raw is None:
            h.issuer_name_raw = member_text
        # Currency: the principal/face unit identifies the instrument currency; the fair-value unit is
        # the statement (reporting) currency used for total reconciliation.
        fv_fact = next((f for f in gfacts if f.fact_id == (h.field_lineage.get("fair_value").source_ref if h.field_lineage.get("fair_value") else None)), None)
        if fv_fact is not None and fv_fact.unit and re.fullmatch(r"[A-Z]{3}", fv_fact.unit):
            h.reporting_currency = fv_fact.unit
            h.fair_value_unit_original = fv_fact.unit  # preserved even when D33 re-assigns reporting_currency
        if h.currency is None:
            instrument_units: list[str] = []
            for fld_name in ("principal_amount", "face_amount"):
                le = h.field_lineage.get(fld_name)
                src = next((f for f in gfacts if le and f.fact_id == le.source_ref), None)
                if src is not None and src.unit and re.fullmatch(r"[A-Z]{3}", src.unit):
                    instrument_units.append(src.unit)
            units = sorted({f.unit for f in gfacts if f.unit and re.fullmatch(r"[A-Z]{3}", f.unit)})
            if instrument_units:
                h.set_field("currency", instrument_units[0], source="xbrl_fact", raw_value=instrument_units[0], source_ref="unit:principal_amount", transformation="unit_measure")
            elif len(units) == 1:
                h.set_field("currency", units[0], source="xbrl_fact", raw_value=units[0], source_ref="unit", transformation="unit_measure")
            elif len(units) > 1:
                h.add_flag("mixed_currencies_in_holding")
        holdings.append(h)
    if skipped_no_monetary:
        notes.append(f"xbrl_groups_without_monetary_values_excluded:{skipped_no_monetary}")
    totals.sort(key=lambda t: (t.field, t.rank, t.dimension_signature, t.fact_id))
    return XbrlExtraction(holdings, totals, len(groups), notes, excluded)
