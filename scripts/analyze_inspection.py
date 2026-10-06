"""Summarize an inspection directory as template-design evidence (development helper, read-only).

Usage: python scripts/analyze_inspection.py output/s2_inspect_<cik>_latest [--labels N]
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd


def main(path: str, n_labels: int = 6) -> None:
    d = Path(path)
    insp = json.load(open(d / "inspection.json"))
    print(f"=== {insp['company_name']} cik={insp['cik']} acc={insp['accession_number']} report={insp['report_date']} template={insp['template_id']} instance={insp['instance']}")
    print("axes:", [(a["axis"].split("}")[-1], a["score"], a["member_count"], "typed" if a["typed"] else "explicit") for a in insp["candidate_holding_axes"][:5]], "selected:", (insp["selected_axis"] or "").split("}")[-1])
    print("mapped:", sorted(insp["mapped_concepts"]))
    print("unmapped SOI:", [u["concept"].split("}")[-1] for u in insp["unmapped_soi_concepts"]][:20])
    tabs = pd.read_csv(d / "html_table_scores.csv", dtype=str, keep_default_na=False)
    acc = tabs[tabs.accepted == "True"]
    print("accepted tables:", len(acc), "period:", Counter(acc.period_status).most_common(), "scale:", Counter(zip(acc.scale_multiplier, acc.scale_source)).most_common(3))
    for hdr, cnt in Counter(acc.flattened_headers).most_common(3):
        print("  header x%d:" % cnt, hdr[:260])
    for h in insp["example_holdings"][:n_labels]:
        ml = json.loads(h["member_labels"])
        print("  label:", list(ml.values())[0][:200] if ml else None)
        print("    ->", {k: str(h.get(k))[:40] for k in ("issuer", "description", "industry", "reference_index", "spread_bps", "maturity_date", "principal_amount", "fair_value", "currency", "source_method")})
    for r in insp["example_rows"][:3]:
        print("  html row:", r["row_text"][:160], "|", r["fields"][:200])
    for rec in insp["reconciliation"]:
        print("  recon", rec["field"], rec["status"], rec["detail_sum"], rec["reported_total"], rec["selected_source"], (rec["notes"] or "")[:120])
    tc = insp["reported_total_candidates"]
    print("  totals rank<=3:", [(t["field"], t["value"], t["source"], (t.get("row_text") or "")[:50]) for t in tc if t["rank"] <= 3][:8])
    print("  flags:", insp["filing_flags"], "errors:", [e["message"][:80] for e in insp["errors"]])


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 4)
