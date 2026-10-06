"""Write company templates from Python dicts (keeps evidence strings next to rules). Development helper.

Usage: python scripts/write_templates.py <batch_module>  (modules under scripts/template_batches/)
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
SECTION_HEADING_RE = re.compile(r"affiliat|control|investments?\b|debt|equity|notes|short-term|cash|total|\(continued\)|warrants|preferred|common|membership|loans|bank|securities|portfolio|first lien|second lien|unitranche", re.IGNORECASE)


def html_industry_headings(cik: str, run: str = "latest") -> list[str]:
    """Industry vocabulary = HTML group-heading rows that are not section/affiliation headings (evidence from the filing)."""
    hr = pd.read_csv(ROOT / "output" / f"s2_generic_{cik}_{run}" / "html_rows.csv", dtype=str, keep_default_na=False)
    heads = hr[hr.classification == "group_heading"].row_text.map(lambda s: re.sub(r"\s*\([^)]*\)\s*$", "", s).strip())
    return sorted({h for h in heads if h and not SECTION_HEADING_RE.search(h) and len(h) < 60})


def write(cik: str, template: dict, header: str) -> Path:
    path = ROOT / "templates" / f"{cik}.yml"
    path.write_text(header + yaml.safe_dump(template, sort_keys=False, allow_unicode=True, width=200), encoding="utf-8")
    return path


def main(module: str) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    mod = importlib.import_module(f"template_batches.{module}")
    for cik, (template, header) in mod.TEMPLATES.items():
        print("wrote", write(cik, template, header))


if __name__ == "__main__":
    main(sys.argv[1])
