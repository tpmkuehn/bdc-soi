"""Targeted triage of one run: where does the fair-value detail sum come from? (development helper)"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd


def main(path: str) -> None:
    d = Path(path)
    h = pd.read_csv(d / "holdings.csv", dtype=str, keep_default_na=False)
    fv = pd.to_numeric(h.fair_value, errors="coerce")
    lin = h.field_lineage.map(json.loads)
    src = lin.map(lambda l: (l.get("fair_value") or {}).get("source"))
    print(f"== {d.name}: rows={len(h)} FV sum={fv.sum():,.0f}")
    print("  FV by lineage source:", {k: f"{fv[src == k].sum():,.0f} (n={int((src == k).sum())})" for k in src.dropna().unique()})
    print("  FV by source_method:", {k: f"{fv[h.source_method == k].sum():,.0f}" for k in h.source_method.unique()})
    print("  FV by currency:", {k: f"{fv[h.currency == k].sum():,.0f}" for k in h.currency.unique()}, "| reporting:", h.reporting_currency.value_counts().to_dict())
    flags = h.review_flags.map(json.loads)
    for key in ("xbrl_subsidiary_context", "html_row_after_total", "html_fallback_no_xbrl_holdings", "unmatched_html_row", "ambiguous_html_match"):
        m = flags.map(lambda fl: any(f.startswith(key) for f in fl))
        if m.any():
            print(f"  {key}: n={int(m.sum())} FV={fv[m].sum():,.0f}", h[m][["issuer", "description", "fair_value"]].head(4).values.tolist())
    html_fv = h[(src == "html_cell") | (src == "html_cell_carry_forward")]
    if len(html_fv):
        print("  html-sourced FV rows sample:", html_fv[["issuer", "description", "fair_value", "currency", "source_method"]].head(5).values.tolist())
    nm = h[flags.map(lambda fl: any(f.startswith("composite_no_match") for f in fl))]
    if len(nm):
        print("  composite_no_match samples:", nm.issuer_name_raw.map(lambda s: s[:140]).head(4).tolist())
    fd = pd.read_csv(d / "filing_diagnostics.csv", dtype=str, keep_default_na=False).iloc[0]
    print("  notes:", fd.notes[:400])
    tc = list(json.load(open(d / "total_candidates.json")).values())[0]
    print("  FV cands rank<=2:", [(t["value"], t["source"], (t.get("row_text") or "")[:50]) for t in tc if t["field"] == "fair_value" and t["rank"] <= 2][:6])


if __name__ == "__main__":
    for p in sys.argv[1:]:
        main(p)
