"""Run-to-run comparison (SPEC 6.5, 20 step 5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from bdc_soi.models import NORMALIZED_FIELDS


def _load(path: Path, name: str) -> pd.DataFrame:
    p = Path(path) / name
    return pd.read_csv(p, dtype=str, keep_default_na=False) if p.exists() else pd.DataFrame()


def compare_runs(before: Path, after: Path, output: Path) -> dict[str, Any]:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    hb, ha = _load(before, "holdings.csv"), _load(after, "holdings.csv")
    vb, va = _load(before, "validation.csv"), _load(after, "validation.csv")
    key = "holding_id"
    b_ids = set(hb[key]) if len(hb) else set()
    a_ids = set(ha[key]) if len(ha) else set()
    added = sorted(a_ids - b_ids)
    removed = sorted(b_ids - a_ids)
    common = sorted(a_ids & b_ids)
    bi = hb.set_index(key) if len(hb) else hb
    ai = ha.set_index(key) if len(ha) else ha
    field_changes: list[dict[str, Any]] = []
    lineage_changes: list[dict[str, Any]] = []
    confidence_changes: list[dict[str, Any]] = []
    flag_changes: list[dict[str, Any]] = []
    for hid in common:
        rb, ra = bi.loc[hid], ai.loc[hid]
        for fld in NORMALIZED_FIELDS:
            vb_, va_ = str(rb.get(fld, "")), str(ra.get(fld, ""))
            if vb_ != va_:
                field_changes.append({"holding_id": hid, "field": fld, "before": vb_, "after": va_})
        try:
            lb, la = json.loads(rb.get("field_lineage", "{}") or "{}"), json.loads(ra.get("field_lineage", "{}") or "{}")
        except json.JSONDecodeError:
            lb, la = {}, {}
        for fld in sorted(set(lb) | set(la)):
            sb, sa = (lb.get(fld) or {}).get("source"), (la.get(fld) or {}).get("source")
            rb_, ra_ = (lb.get(fld) or {}).get("rule_id"), (la.get(fld) or {}).get("rule_id")
            if sb != sa or rb_ != ra_:
                lineage_changes.append({"holding_id": hid, "field": fld, "before_source": sb, "after_source": sa, "before_rule": rb_, "after_rule": ra_})
        try:
            cb, ca = float(rb.get("extraction_confidence") or 0), float(ra.get("extraction_confidence") or 0)
        except ValueError:
            cb, ca = 0.0, 0.0
        if abs(cb - ca) > 1e-9:
            confidence_changes.append({"holding_id": hid, "before": cb, "after": ca, "delta": round(ca - cb, 4)})
        fb, fa = rb.get("review_flags", "[]"), ra.get("review_flags", "[]")
        if fb != fa:
            flag_changes.append({"holding_id": hid, "before": fb, "after": fa})
    recon: list[dict[str, Any]] = []
    if len(vb) and len(va):
        kb = vb.set_index(["accession_number", "field"])
        ka = va.set_index(["accession_number", "field"])
        for idx in sorted(set(kb.index) | set(ka.index)):
            sb = kb.loc[idx]["status"] if idx in kb.index else None
            sa = ka.loc[idx]["status"] if idx in ka.index else None
            if sb != sa:
                recon.append({"accession_number": idx[0], "field": idx[1], "before": sb, "after": sa})
    per_filing: list[dict[str, Any]] = []
    for acc in sorted(set(ha["accession_number"]) | set(hb["accession_number"])) if (len(ha) or len(hb)) else []:
        nb = int((hb["accession_number"] == acc).sum()) if len(hb) else 0
        na = int((ha["accession_number"] == acc).sum()) if len(ha) else 0
        per_filing.append({"accession_number": acc, "rows_before": nb, "rows_after": na, "delta": na - nb, "material_row_movement": abs(na - nb) > max(2, 0.05 * max(nb, 1))})
    summary = {
        "before": str(before),
        "after": str(after),
        "rows_before": len(hb),
        "rows_after": len(ha),
        "rows_added": len(added),
        "rows_removed": len(removed),
        "field_changes": len(field_changes),
        "lineage_changes": len(lineage_changes),
        "confidence_changes": len(confidence_changes),
        "review_flag_changes": len(flag_changes),
        "reconciliation_changes": recon,
        "per_filing": per_filing,
        "material_deterioration": any(p["material_row_movement"] and p["delta"] < 0 for p in per_filing) or any(r["after"] in {"fail", "ambiguous_total"} and r["before"] == "pass" for r in recon),
    }
    pd.DataFrame({"holding_id": added}).to_csv(output / "rows_added.csv", index=False, lineterminator="\n")
    pd.DataFrame({"holding_id": removed}).to_csv(output / "rows_removed.csv", index=False, lineterminator="\n")
    pd.DataFrame(field_changes).to_csv(output / "field_changes.csv", index=False, lineterminator="\n")
    pd.DataFrame(lineage_changes).to_csv(output / "lineage_changes.csv", index=False, lineterminator="\n")
    pd.DataFrame(confidence_changes).to_csv(output / "confidence_changes.csv", index=False, lineterminator="\n")
    pd.DataFrame(flag_changes).to_csv(output / "review_flag_changes.csv", index=False, lineterminator="\n")
    (output / "comparison.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary
