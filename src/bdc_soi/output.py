"""Run artifacts: Parquet, CSV, JSON, Excel and the run manifest (SPEC 18)."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

import pandas as pd

from bdc_soi import ENGINE_VERSION
from bdc_soi.models import HOLDING_COLUMNS, as_jsonable
from bdc_soi.pipeline import FilingResult, RunContext

REQUIRED_ARTIFACTS = [
    "run_manifest.json", "all_filings.parquet", "latest_filings.parquet", "holdings.parquet", "holdings.csv",
    "long_xbrl_facts.parquet", "filing_diagnostics.csv", "axis_diagnostics.csv", "html_table_diagnostics.csv",
    "matching_diagnostics.csv", "validation.csv", "template_usage.csv", "review_queue.csv", "output.xlsx",
]
PACKAGES = ["arelle-release", "requests", "pandas", "openpyxl", "beautifulsoup4", "lxml", "pyyaml", "pydantic", "rapidfuzz", "pyarrow", "jsonschema", "pytest"]
_FIXED_XLSX_TIME = datetime(2000, 1, 1, 0, 0, 0)


class OutputExistsError(RuntimeError):
    pass


def _df(rows: list[dict[str, Any]], columns: list[str] | None = None) -> pd.DataFrame:
    if rows:
        df = pd.DataFrame(rows)
        if columns:
            for c in columns:
                if c not in df.columns:
                    df[c] = None
            df = df[columns + [c for c in df.columns if c not in columns]]
        return df
    return pd.DataFrame(columns=columns or [])


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    df = df.astype(object).where(pd.notnull(df), None) if len(df) else df
    df.to_parquet(path, index=False)


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, lineterminator="\n", encoding="utf-8")


def package_versions() -> dict[str, str]:
    out: dict[str, str] = {}
    for p in PACKAGES:
        try:
            out[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            out[p] = "not installed"
    return out


def git_commit() -> str | None:
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=False)
        return res.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def prepare_output_dir(path: Path, force: bool = False) -> Path:
    path = Path(path)
    if path.exists() and any(path.iterdir()):
        if not force:
            raise OutputExistsError(f"output directory {path} already contains artifacts; choose a new directory to preserve prior runs (or pass --force to overwrite)")
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_run(ctx: RunContext, results: list[FilingResult], out_dir: Path, *, started: datetime, run_id: str, command: str, universe: list[str] | None = None) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = ctx.config

    filings_rows: list[dict[str, Any]] = []
    latest_rows: list[dict[str, Any]] = []
    seen_ciks: set[str] = set()
    for r in results:
        if r.discovery and r.cik not in seen_ciks:
            seen_ciks.add(r.cik)
            for f in r.discovery.filings:
                filings_rows.append(f.to_row())
            if r.discovery.selected:
                latest_rows.append(r.discovery.selected.to_row())
    filings_rows.sort(key=lambda x: (x["cik"], x["filing_date"] or "", x["accession_number"]))
    holding_rows = [h.to_row() for r in results for h in r.holdings]
    holding_rows.sort(key=lambda x: (x["cik"], x["accession_number"], x["holding_id"]))
    facts_rows = [f.to_row() | {"cik": r.cik, "accession_number": r.accession_number} for r in results for f in r.facts] if cfg.extraction.write_long_xbrl_facts else []
    filing_diag_rows = [r.diagnostic.to_row() for r in results]
    axis_rows = [a.to_row() | {"cik": r.cik, "accession_number": r.accession_number} for r in results for a in r.axis_scores]
    table_rows = [t.to_row() | {"cik": r.cik, "accession_number": r.accession_number} for r in results for t in r.tables]
    match_rows = [m.to_row() | {"cik": r.cik, "accession_number": r.accession_number} for r in results for m in r.matches]
    validation_rows = [v.to_row(r.cik, r.accession_number or "") for r in results for v in r.reconciliations]
    template_rows = [
        {
            "cik": r.cik,
            "accession_number": r.accession_number,
            "report_date": r.diagnostic.report_date.isoformat() if r.diagnostic.report_date else None,
            "template_id": r.diagnostic.template_id,
            "template_kind": "company" if r.template else "generic",
            "selection_reason": r.template_reason,
            "composite_rules": json.dumps([c.id for c in (r.template.composite_fields if r.template else [])]),
            "holdings": len(r.holdings),
            "status": r.diagnostic.status,
        }
        for r in results
    ]
    review_rows = [i.to_row() for r in results for i in r.review_items]
    html_rows = [row.to_row() | {"cik": r.cik, "accession_number": r.accession_number, "classification": row.classification} for r in results for t in r.tables if t.accepted for row in t.rows]
    role_rows = [{"cik": r.cik, "accession_number": r.accession_number, "uri": x.uri, "definition": x.definition, "candidate": x.is_candidate, "pattern": x.matched_pattern, "concepts": x.concept_count} for r in results for x in r.roles]
    errors = [e.model_dump() for r in results for e in r.errors]
    excluded_rows = [c.to_row() | {"cik": r.cik, "accession_number": r.accession_number, "report_date": r.diagnostic.report_date.isoformat() if r.diagnostic.report_date else None} for r in results for c in r.excluded_candidates]

    _write_parquet(_df(filings_rows), out_dir / "all_filings.parquet")
    _write_parquet(_df(latest_rows), out_dir / "latest_filings.parquet")
    hdf = _df(holding_rows, list(HOLDING_COLUMNS))
    _write_parquet(hdf, out_dir / "holdings.parquet")
    _write_csv(hdf, out_dir / "holdings.csv")
    _write_parquet(_df(facts_rows), out_dir / "long_xbrl_facts.parquet")
    _write_csv(_df(filing_diag_rows), out_dir / "filing_diagnostics.csv")
    _write_csv(_df(axis_rows), out_dir / "axis_diagnostics.csv")
    _write_csv(_df(table_rows), out_dir / "html_table_diagnostics.csv")
    _write_csv(_df(match_rows), out_dir / "matching_diagnostics.csv")
    _write_csv(_df(validation_rows), out_dir / "validation.csv")
    _write_csv(_df(template_rows), out_dir / "template_usage.csv")
    _write_csv(_df(review_rows), out_dir / "review_queue.csv")
    _write_csv(_df(excluded_rows), out_dir / "excluded_candidates.csv")
    _write_csv(_df(validation_rows), out_dir / "reconciliation_bridge.csv")
    _write_csv(_df(html_rows), out_dir / "html_rows.csv")
    _write_csv(_df(role_rows), out_dir / "presentation_roles.csv")
    (out_dir / "errors.json").write_text(json.dumps(errors, indent=2, default=str), encoding="utf-8")
    (out_dir / "total_candidates.json").write_text(json.dumps({f"{r.cik}/{r.accession_number}": r.total_candidates for r in results}, indent=2, default=str, sort_keys=True), encoding="utf-8")
    (out_dir / "holdings.json").write_text(json.dumps([as_jsonable(h.model_dump(mode="json")) for r in results for h in sorted(r.holdings, key=lambda h: h.holding_id)], indent=1, default=str), encoding="utf-8")
    (out_dir / "inspection.json").write_text(json.dumps([r.inspection for r in results], indent=1, default=str), encoding="utf-8")

    # Excel: display formatting only (spread_output_format), long facts optional.
    _write_excel(out_dir / "output.xlsx", hdf, filing_diag_rows, validation_rows, review_rows, template_rows, facts_rows if cfg.extraction.excel_long_facts else None, results)

    finished = datetime.now(timezone.utc)
    manifest = {
        "run_id": run_id,
        "command": command,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "engine_version": ENGINE_VERSION,
        "git_commit": git_commit(),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "package_versions": package_versions(),
        "configuration_checksum": cfg.checksum(),
        "configuration": json.loads(json.dumps(cfg.model_dump(mode="json") | {"sec": {**cfg.sec.model_dump(), "user_agent": "<redacted>"}})),
        "template_checksums": ctx.registry.checksums(),
        "offline": ctx.offline,
        "universe": universe,
        "selected_filings": [
            {
                "cik": r.cik,
                "company_name": r.diagnostic.company_name,
                "accession_number": r.accession_number,
                "form": r.filing.form if r.filing else None,
                "filing_date": r.filing.filing_date.isoformat() if r.filing and r.filing.filing_date else None,
                "report_date": r.diagnostic.report_date.isoformat() if r.diagnostic.report_date else None,
                "template_id": r.diagnostic.template_id,
                "instance": r.diagnostic.instance_document,
                "instance_kind": r.diagnostic.instance_kind,
                "status": r.diagnostic.status,
                "accession_checksums": r.package.checksums() if r.package else {},
            }
            for r in results
        ],
        "row_counts": {
            "holdings": len(holding_rows),
            "filings": len(filings_rows),
            "long_xbrl_facts": len(facts_rows),
            "html_rows": len(html_rows),
            "review_queue": len(review_rows),
            "validation": len(validation_rows),
            "excluded_candidates": len(excluded_rows),
        },
        "exceptions": [{k: v for k, v in e.items() if k != "traceback"} for e in errors],
        "artifacts": sorted(p.name for p in out_dir.iterdir()),
        "nondeterministic_fields": ["run_id", "started_at", "finished_at", "git_commit", "platform"],
    }
    (out_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return manifest


def _write_excel(path: Path, holdings: pd.DataFrame, filing_rows, validation_rows, review_rows, template_rows, facts_rows, results: list[FilingResult]) -> None:
    display = holdings.copy()
    fmt = "decimal"
    for r in results:
        if r.template:
            fmt = r.template.normalization.spread_output_format
            break
    if "spread" in display.columns and len(display):
        if fmt == "percent":
            display.insert(list(display.columns).index("spread") + 1, "spread_display", display["spread"].map(lambda v: f"{v * 100:.2f}%" if isinstance(v, (int, float)) and pd.notnull(v) else None))
        elif fmt == "basis_points":
            display.insert(list(display.columns).index("spread") + 1, "spread_display", display["spread_bps"].map(lambda v: f"{v:.0f} bps" if isinstance(v, (int, float)) and pd.notnull(v) else None))
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        display.to_excel(writer, sheet_name="holdings", index=False)
        _df(filing_rows).to_excel(writer, sheet_name="filing_diagnostics", index=False)
        _df(validation_rows).to_excel(writer, sheet_name="validation", index=False)
        _df(review_rows).to_excel(writer, sheet_name="review_queue", index=False)
        _df(template_rows).to_excel(writer, sheet_name="template_usage", index=False)
        if facts_rows is not None:
            _df(facts_rows).to_excel(writer, sheet_name="long_xbrl_facts", index=False)
        book = writer.book
        book.properties.created = _FIXED_XLSX_TIME
        book.properties.modified = _FIXED_XLSX_TIME
        book.properties.lastModifiedBy = "bdc_soi"
        book.properties.creator = "bdc_soi"
    _normalize_zip_timestamps(path)


def _normalize_zip_timestamps(path: Path) -> None:
    """Rewrite the xlsx ZIP with fixed entry timestamps so identical content yields identical bytes."""
    import shutil
    import zipfile

    tmp = path.with_suffix(".tmp.xlsx")
    with zipfile.ZipFile(path, "r") as src, zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                import re as _re

                data = _re.sub(rb"<dcterms:modified([^>]*)>[^<]*</dcterms:modified>", rb"<dcterms:modified\1>2000-01-01T00:00:00Z</dcterms:modified>", data)
            new = zipfile.ZipInfo(info.filename, date_time=(1980, 1, 1, 0, 0, 0))
            new.compress_type = zipfile.ZIP_DEFLATED
            new.external_attr = info.external_attr
            dst.writestr(new, data)
    shutil.move(str(tmp), str(path))
