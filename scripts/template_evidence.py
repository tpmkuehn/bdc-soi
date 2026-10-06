"""Collect template-authoring evidence from a generic extract directory (development helper, read-only).

Usage: python scripts/template_evidence.py output/s2_generic_<cik>_latest
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

INDEX_TOKEN_RE = re.compile(r"\b([A-Z]{1,6})\s*(?:\([A-Z]\))?\s*\+")


def main(path: str) -> None:
    d = Path(path)
    h = pd.read_csv(d / "holdings.csv", dtype=str, keep_default_na=False)
    hr = pd.read_csv(d / "html_rows.csv", dtype=str, keep_default_na=False)
    fd = pd.read_csv(d / "filing_diagnostics.csv", dtype=str, keep_default_na=False).iloc[0]
    v = pd.read_csv(d / "validation.csv", dtype=str, keep_default_na=False)
    tabs = pd.read_csv(d / "html_table_diagnostics.csv", dtype=str, keep_default_na=False)
    print(f"=== {fd.company_name} cik={fd.cik} acc={fd.accession_number} report={fd.report_date} status={fd.status} xbrl={fd.xbrl_holdings} html_rows={fd.html_rows} matched={fd.matched_rows} unmatched={fd.unmatched_html_rows}")
    print("  recon:", [(r.field, r.status, r.detail_sum, r.reported_total, r.selected_source) for r in v.itertuples()])
    x = h[h.source_method != "html_only"]
    labels = x.holding_member_key.str.replace("^typed:", "", regex=True)
    pipes = Counter(l.count("|") for l in labels)
    print("  label '|' counts:", pipes.most_common(4), "| ' - ' counts:", Counter(l.count(" - ") for l in labels).most_common(3))
    print("  label samples:", [l[:150] for l in labels.sample(min(3, len(labels)), random_state=1)])
    kw = Counter(k for l in labels for k in re.findall(r"\b(Investment Type|Security Type|Interest Rate|Maturity Date|Maturity|Reference Rate and Spread|Spread Above Index|Index|Spread|Floor|Industry|Acquisition Date|Type)\b", l))
    print("  label keywords:", kw.most_common(8))
    acc = tabs[tabs.accepted == "True"]
    print("  tables accepted:", len(acc), "scale:", Counter(zip(acc.scale_multiplier, acc.scale_source)).most_common(2), "headers:", Counter(acc.flattened_headers).most_common(1)[0][0][:220] if len(acc) else None)
    heads = hr[hr.classification == "group_heading"].row_text.map(lambda s: s[:60]).value_counts().head(8).to_dict()
    print("  group headings:", heads)
    tot = hr[hr.classification.isin(["total", "subtotal"])].row_text.map(lambda s: s[:70]).value_counts().head(5).to_dict()
    print("  total/subtotal rows:", tot)
    rate_texts = [json.loads(f).get("interest_rate_text") for f in hr[hr.classification == "holding"].fields]
    toks = Counter(m for t in rate_texts if t for m in INDEX_TOKEN_RE.findall(t))
    print("  html index tokens:", toks.most_common(8), "| rate text samples:", [t for t in rate_texts if t][:3])
    print("  xbrl reference_index values:", x.reference_index.value_counts().head(5).to_dict())
    xfv = x.fair_value.replace("", "0").astype(float).abs(); hfv = pd.to_numeric(hr[hr.classification == "holding"].fields.map(lambda f: json.loads(f).get("fair_value")), errors="coerce").dropna().abs()
    if len(xfv) and len(hfv):
        print(f"  median FV xbrl={xfv.median():,.0f} html={hfv.median():,.0f} ratio={xfv.median()/max(hfv.median(),1):.2f}")
    neg = (x.fair_value.replace("", "0").astype(float) < 0).sum()
    print("  negative FV (xbrl rows):", int(neg), "| flags:", Counter(f.split(':')[0] for fl in h.review_flags for f in json.loads(fl)).most_common(6))
    hy = h[h.source_method == "hybrid_xbrl_html"]
    if len(hy):
        ac = pd.to_numeric(hy.amortized_cost, errors="coerce"); co = pd.to_numeric(hy.cost, errors="coerce")
        both = ac.notna() & co.notna()
        if both.sum():
            print(f"  hybrid rows with html amortized_cost & xbrl cost: {int(both.sum())}, equal within 1: {int(((ac - co).abs() <= 1)[both].sum())}")
    print("  filing flags:", fd.notes[:200])


if __name__ == "__main__":
    main(sys.argv[1])
