"""Command-line interface (SPEC 6)."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from bdc_soi import ENGINE_VERSION
from bdc_soi.config import USER_AGENT_SETUP_MESSAGE, AppConfig, ContactEmailError, is_genuine_user_agent, load_config, resolve_user_agent
from bdc_soi.sec_client import SecClient, is_illustrative_accession, normalize_cik
from bdc_soi.templates import TemplateRegistry, TemplateValidationError, validate_against_json_schema, write_json_schema

log = logging.getLogger("bdc_soi")


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", default=None, help="application.yml path (default: config/application.yml)")
    p.add_argument("--templates", default=None, help="templates directory (default from config)")
    p.add_argument("--cache", default=None, help="cache directory (default from config)")
    p.add_argument("--offline", action="store_true", help="never touch the network; use cached filings and taxonomies")
    p.add_argument(
        "--sec-email",
        default=None,
        metavar="EMAIL",
        help="monitored contact email for the SEC User-Agent (required for live retrieval unless SEC_USER_AGENT is set; place it after the subcommand, e.g. extract --cik ... --sec-email EMAIL)",
    )
    p.add_argument("--sec-organization", default=None, metavar="NAME", help="optional organization name placed before the application name in the SEC User-Agent (use with --sec-email)")
    p.add_argument("--log-level", default="INFO")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bdc_soi", description="BDC Schedule of Investments extraction engine")
    parser.add_argument("--version", action="version", version=f"bdc_soi {ENGINE_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("extract", help="extract one filing")
    p.add_argument("--cik", required=True)
    p.add_argument("--accession", default=None)
    p.add_argument("--latest", action="store_true", help="use the latest eligible 10-Q (default when --accession omitted)")
    p.add_argument("--output", required=True)
    p.add_argument("--force", action="store_true", help="overwrite an existing non-empty output directory")
    _common(p)

    p = sub.add_parser("extract-universe", help="extract every enabled company in a universe file")
    p.add_argument("--universe", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--force", action="store_true")
    _common(p)

    p = sub.add_parser("inspect", help="inspect a filing's roles, concepts, axes and HTML tables")
    p.add_argument("--cik", required=True)
    p.add_argument("--accession", default=None)
    p.add_argument("--latest", action="store_true", help="use the latest eligible 10-Q (default when --accession omitted)")
    p.add_argument("--output", required=True)
    p.add_argument("--force", action="store_true")
    _common(p)

    p = sub.add_parser("validate-templates", help="validate template files against schema and semantic rules")
    p.add_argument("--templates", default="templates")
    p.add_argument("--schema", default="config/template.schema.json")
    p.add_argument("--write-schema", action="store_true", help="regenerate the JSON schema file from the typed model")
    p.add_argument("--log-level", default="INFO")

    p = sub.add_parser("evaluate", help="evaluate a run against the golden dataset")
    p.add_argument("--actual", required=True)
    p.add_argument("--golden", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--splits", default=None, help="comma-separated splits to include (development,regression,holdout)")
    p.add_argument("--include-unreviewed", action="store_true", help="also score unreviewed candidate annotations (never counts toward acceptance)")
    p.add_argument("--log-level", default="INFO")

    p = sub.add_parser("compare", help="compare two runs")
    p.add_argument("--before", required=True)
    p.add_argument("--after", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--log-level", default="INFO")

    p = sub.add_parser("review-package", help="build the Excel human-review workbook (summary + stratified candidate batch)")
    p.add_argument("--runs", nargs="+", required=True, help="run directories (universe and prior-period runs)")
    p.add_argument("--output", required=True)
    p.add_argument("--per-company", type=int, default=12, help="full profile: rows per company/period; triage profile: ordinary rows per period")
    p.add_argument("--seed", type=int, default=20261006)
    p.add_argument("--profile", choices=["full", "triage"], default="full", help="triage = small first batch (ordinary rows per period + round-robin blockers)")
    p.add_argument("--blocker-budget", type=int, default=40, help="triage profile: maximum blocker rows across the batch")
    p.add_argument("--blocker-inventory", default=None, help="also write the complete (unsampled) blocker inventory CSV to this path")
    p.add_argument("--log-level", default="INFO")

    p = sub.add_parser("import-review", help="validate a filled review workbook and write reviewed rows to golden/expected")
    p.add_argument("--workbook", required=True)
    p.add_argument("--golden", required=True)
    p.add_argument("--log-level", default="INFO")

    p = sub.add_parser("annotate", help="export a run's holdings as UNREVIEWED golden annotation candidates")
    p.add_argument("--actual", required=True)
    p.add_argument("--golden", required=True)
    p.add_argument("--accession", required=True)
    p.add_argument("--log-level", default="INFO")
    return parser


def _setup_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stderr)


def _context(args: argparse.Namespace):
    from bdc_soi.pipeline import RunContext

    overrides = {}
    if args.templates:
        overrides["paths.templates"] = args.templates
    if args.cache:
        overrides["paths.cache"] = args.cache
    if args.offline:
        overrides["extraction.offline"] = True
    sec_email = getattr(args, "sec_email", None)
    sec_organization = getattr(args, "sec_organization", None)
    if sec_email is not None or sec_organization is not None:
        # An explicit contact is validated here, before any configuration or network activity.
        user_agent, source = resolve_user_agent(sec_email, sec_organization, env={})
        overrides["sec.user_agent"] = user_agent
        overrides["sec.user_agent_source"] = source
    cfg: AppConfig = load_config(args.config, overrides)
    offline = cfg.extraction.offline
    if not offline and not is_genuine_user_agent(cfg.sec.user_agent):
        # Fail before any SEC request (filing download or Arelle taxonomy retrieval) is attempted.
        raise ContactEmailError(USER_AGENT_SETUP_MESSAGE)
    registry = TemplateRegistry.from_directory(cfg.resolve("templates"))
    registry.raise_if_invalid()  # SPEC 23: template validation failure stops before extraction
    cache_dir = cfg.resolve("cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    client = SecClient(cfg.sec, cache_dir, offline=offline)
    return RunContext(config=cfg, registry=registry, client=client, cache_dir=cache_dir, offline=offline)


def _run_id(parts: list[str], started: datetime) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{started.strftime('%Y%m%dT%H%M%SZ')}-{digest}"


def cmd_extract(args: argparse.Namespace) -> int:
    from bdc_soi.output import prepare_output_dir, write_run
    from bdc_soi.pipeline import process_filing

    if args.accession and is_illustrative_accession(args.accession):
        log.error("accession %s is the specification's illustrative placeholder; supply a real accession or --latest", args.accession)
        return 2
    ctx = _context(args)
    out = prepare_output_dir(Path(args.output), args.force)
    started = datetime.now(timezone.utc)
    result = process_filing(ctx, args.cik, args.accession)
    manifest = write_run(ctx, [result], out, started=started, run_id=_run_id([args.cik, args.accession or "latest", ENGINE_VERSION], started), command="extract")
    _print_summary([result], out, manifest)
    return 0 if result.diagnostic.status != "failed" else 1


def cmd_extract_universe(args: argparse.Namespace) -> int:
    from bdc_soi.output import prepare_output_dir, write_run
    from bdc_soi.pipeline import process_filing

    ctx = _context(args)
    universe = yaml.safe_load(Path(args.universe).read_text(encoding="utf-8")) or {}
    companies = [c for c in universe.get("companies", []) if c.get("enabled", True)]
    out = prepare_output_dir(Path(args.output), args.force)
    started = datetime.now(timezone.utc)
    results = []
    for c in companies:
        cik = normalize_cik(c["cik"])
        acc = c.get("accession")
        try:
            results.append(process_filing(ctx, cik, acc))
        except Exception as exc:  # a filing failure must not terminate the universe run (SPEC 23)
            from bdc_soi.models import FilingDiagnostic
            from bdc_soi.pipeline import FilingResult

            fr = FilingResult(cik=cik, accession_number=acc, diagnostic=FilingDiagnostic(cik=cik, accession_number=acc or "", status="failed"))
            fr.record_error("universe_dispatch", exc)
            results.append(fr)
    manifest = write_run(ctx, results, out, started=started, run_id=_run_id([c["cik"] for c in companies] + [ENGINE_VERSION], started), command="extract-universe", universe=[normalize_cik(c["cik"]) for c in companies])
    _print_summary(results, out, manifest)
    return 0 if all(r.diagnostic.status != "failed" for r in results) else 1


def cmd_inspect(args: argparse.Namespace) -> int:
    from bdc_soi.output import prepare_output_dir
    from bdc_soi.pipeline import process_filing

    if args.accession and is_illustrative_accession(args.accession):
        log.error("accession %s is illustrative; supply a real accession", args.accession)
        return 2
    ctx = _context(args)
    out = prepare_output_dir(Path(args.output), args.force)
    result = process_filing(ctx, args.cik, args.accession)
    (out / "inspection.json").write_text(json.dumps(result.inspection, indent=2, default=str), encoding="utf-8")
    import pandas as pd

    pd.DataFrame([a.to_row() for a in result.axis_scores]).to_csv(out / "axis_candidates.csv", index=False, lineterminator="\n")
    pd.DataFrame([t.to_row() for t in result.tables]).to_csv(out / "html_table_scores.csv", index=False, lineterminator="\n")
    pd.DataFrame([{"concept": f.concept_clark, "label": f.standard_label, "mapped_field": f.mapped_field, "rule": f.mapping_rule, "in_soi_role": f.in_soi_role} for f in {x.concept_clark: x for x in result.facts}.values()]).to_csv(out / "concept_mapping.csv", index=False, lineterminator="\n")
    pd.DataFrame([{"uri": r.uri, "definition": r.definition, "candidate": r.is_candidate, "concepts": r.concept_count} for r in result.roles]).to_csv(out / "presentation_roles.csv", index=False, lineterminator="\n")
    insp = result.inspection
    print(f"Inspection written to {out}")
    print(f"  company={insp['company_name']} accession={insp['accession_number']} report_date={insp['report_date']} template={insp['template_id']} ({insp['template_reason']})")
    print(f"  instance={insp['instance']} selected_axis={insp['selected_axis']}")
    print(f"  candidate roles={sum(1 for r in insp['presentation_roles'] if r['candidate'])}/{len(insp['presentation_roles'])} mapped fields={sorted(insp['mapped_concepts'])}")
    print(f"  unmapped SOI concepts={len(insp['unmapped_soi_concepts'])} accepted tables={len(insp['inferred_column_mappings'])} holdings={len(result.holdings)}")
    for rec in insp["reconciliation"]:
        print(f"  reconciliation {rec['field']}: {rec['status']} detail={rec['detail_sum']} reported={rec['reported_total']}")
    for e in insp["errors"]:
        print(f"  ERROR phase={e['phase']} {e['exception_type']}: {e['message']}")
    return 0 if result.diagnostic.status != "failed" else 1


def cmd_validate_templates(args: argparse.Namespace) -> int:
    tdir = Path(args.templates)
    schema = Path(args.schema)
    if args.write_schema or not schema.exists():
        schema.parent.mkdir(parents=True, exist_ok=True)
        write_json_schema(schema)
        print(f"wrote JSON schema to {schema}")
    issues: list[str] = []
    for p in sorted(tdir.glob("*.yml")) + sorted(tdir.glob("*.yaml")):
        issues.extend(validate_against_json_schema(p, schema))
    registry = TemplateRegistry.from_directory(tdir)
    issues.extend(registry.issues)
    for lt in registry.loaded:
        statuses = ", ".join(f"{t.id}[{t.status}]" for t in lt.file.templates)
        print(f"{lt.path.name}: cik={lt.file.cik} templates={len(lt.file.templates)} ({statuses}) sha256={lt.sha256[:12]}")
    if issues:
        print("TEMPLATE VALIDATION FAILED:")
        for i in issues:
            print(f"  - {i}")
        return 1
    print(f"OK: {len(registry.loaded)} template file(s) valid")
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    from bdc_soi.evaluation import evaluate_run

    splits = [s.strip() for s in args.splits.split(",")] if args.splits else None
    report = evaluate_run(Path(args.actual), Path(args.golden), Path(args.report), splits=splits, include_unreviewed=args.include_unreviewed)
    print((Path(args.report) / "summary.md").read_text(encoding="utf-8"))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    from bdc_soi.compare import compare_runs

    summary = compare_runs(Path(args.before), Path(args.after), Path(args.output))
    print(json.dumps({k: v for k, v in summary.items() if k != "per_filing"}, indent=2, default=str))
    return 0


def cmd_annotate(args: argparse.Namespace) -> int:
    from bdc_soi.evaluation import write_candidate_annotations

    path = write_candidate_annotations(Path(args.actual), Path(args.golden), args.accession)
    print(f"wrote UNREVIEWED candidate annotations to {path}; a human reviewer must approve before use as golden data")
    return 0


def cmd_review_package(args: argparse.Namespace) -> int:
    from bdc_soi.review_package import build_review_workbook

    info = build_review_workbook([Path(r) for r in args.runs], Path(args.output), per_company=args.per_company, seed=args.seed, profile=args.profile, blocker_budget=args.blocker_budget)
    if args.blocker_inventory:
        from bdc_soi.review_package import blocker_inventory

        inv = blocker_inventory([Path(r) for r in args.runs])
        Path(args.blocker_inventory).parent.mkdir(parents=True, exist_ok=True)
        inv.to_csv(args.blocker_inventory, index=False)
        print(f"wrote blocker inventory {args.blocker_inventory}: {len(inv)} rows (unsampled)")
    print(f"wrote {info['path']}: {info['summary_rows']} company/period rows, {info['review_rows']} candidate rows, strata {info['strata']}")
    print("All candidate rows are UNREVIEWED; this batch alone does not establish production thresholds.")
    return 0


def cmd_import_review(args: argparse.Namespace) -> int:
    from bdc_soi.review_package import import_review

    info = import_review(Path(args.workbook), Path(args.golden))
    if info["problems"]:
        print("IMPORT REJECTED; fix these rows and rerun:")
        for p in info["problems"]:
            print("  -", p)
        return 1
    print(f"imported {info['accepted_rows']} reviewed rows: {info['written']} (manifests set to review_status: reviewed, review_scope: sample)")
    return 0


def _print_summary(results, out: Path, manifest: dict) -> None:
    print(f"Run {manifest['run_id']} written to {out}")
    for r in results:
        d = r.diagnostic
        print(f"  {r.cik} {r.accession_number} [{d.status}] company={d.company_name} report_date={d.report_date} template={d.template_id} holdings={d.holdings_count} xbrl={d.xbrl_status} html={d.html_status} fv_recon={d.fair_value_reconciliation} cost_recon={d.cost_reconciliation}")
        for e in d.errors:
            print(f"    ERROR phase={e['phase']} {e['type']}: {e['message']}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(getattr(args, "log_level", "INFO"))
    handlers = {
        "extract": cmd_extract,
        "extract-universe": cmd_extract_universe,
        "inspect": cmd_inspect,
        "validate-templates": cmd_validate_templates,
        "evaluate": cmd_evaluate,
        "compare": cmd_compare,
        "annotate": cmd_annotate,
        "review-package": cmd_review_package,
        "import-review": cmd_import_review,
    }
    try:
        return handlers[args.command](args)
    except TemplateValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ContactEmailError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
