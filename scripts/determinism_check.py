"""Compare two runs artifact-by-artifact (SHA-256) excluding operational manifest fields. Development helper.

Usage: python scripts/determinism_check.py output/universe_s2_run3 output/universe_s2_run4
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ARTIFACTS = ["holdings.csv", "holdings.parquet", "holdings.json", "validation.csv", "matching_diagnostics.csv", "axis_diagnostics.csv",
             "html_table_diagnostics.csv", "review_queue.csv", "long_xbrl_facts.parquet", "all_filings.parquet", "latest_filings.parquet",
             "template_usage.csv", "filing_diagnostics.csv", "html_rows.csv", "total_candidates.json", "output.xlsx", "presentation_roles.csv", "errors.json"]


def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main(a: str, b: str) -> int:
    pa, pb = Path(a), Path(b)
    same, diff = [], []
    for name in ARTIFACTS:
        if not (pa / name).exists() or not (pb / name).exists():
            diff.append(f"{name}: missing")
            continue
        (same if digest(pa / name) == digest(pb / name) else diff).append(name)
    m1, m2 = json.loads((pa / "run_manifest.json").read_text()), json.loads((pb / "run_manifest.json").read_text())
    nd = set(m1.get("nondeterministic_fields", [])) | {"command"}
    mdiff = [k for k in m1 if k not in nd and m1.get(k) != m2.get(k)]
    print(f"identical artifacts: {len(same)}/{len(ARTIFACTS)}")
    print("differing artifacts:", diff or "none")
    print("manifest keys differing outside operational fields:", mdiff or "none")
    return 0 if not diff and not mdiff else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
