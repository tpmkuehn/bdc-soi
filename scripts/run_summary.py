"""One-line-per-run summary of extraction runs (development helper, read-only).

Usage: python scripts/run_summary.py output/s2_t1_*  (directories)
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd


def summarize(d: Path) -> str:
    fd = pd.read_csv(d / "filing_diagnostics.csv", dtype=str, keep_default_na=False).iloc[0]
    h = pd.read_csv(d / "holdings.csv", dtype=str, keep_default_na=False)
    v = pd.read_csv(d / "validation.csv", dtype=str, keep_default_na=False)
    rec = {r.field: (r.status, r.detail_sum, r.reported_total) for r in v.itertuples()}
    flags = Counter(f.split(":")[0] for fl in h.review_flags for f in json.loads(fl))
    src = h.source_method.value_counts().to_dict()
    nulls = {k: int((h[k] == "").sum()) for k in ("issuer", "description", "industry", "maturity_date", "fair_value")}
    conf = round(pd.to_numeric(h.extraction_confidence, errors="coerce").mean(), 3) if len(h) else None
    fv = rec.get("fair_value", ("-", "", ""))
    co = rec.get("cost", ("-", "", ""))
    return (f"{d.name}: {fd.company_name[:28]:28} {fd.report_date} tmpl={fd.template_id[:30]:30} st={fd.status} n={len(h)} hyb={src.get('hybrid_xbrl_html',0)} x={src.get('xbrl',0)} ho={src.get('html_only',0)} "
            f"FV={fv[0]}({fv[1][:12]}/{fv[2][:12]}) COST={co[0]}({co[1][:12]}/{co[2][:12]}) nulls={nulls} conf={conf} flags={flags.most_common(5)} notes={fd.notes[:120]}")


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        p = Path(arg)
        if (p / "filing_diagnostics.csv").exists():
            try:
                print(summarize(p))
            except Exception as exc:  # noqa: BLE001 - helper output only
                print(f"{p.name}: ERROR {exc}")
