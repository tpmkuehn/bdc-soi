"""Shared fixtures. Routine tests are offline; live tests require BDC_SOI_LIVE=1 and SEC_USER_AGENT."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from bdc_soi.config import AppConfig, load_config
from bdc_soi.filing_package import FilingPackage, choose_instance
from bdc_soi.models import PackageFile
from bdc_soi.sec_client import SecClient, sha256_of_file
from bdc_soi.templates import TemplateRegistry

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
SYN = FIXTURES / "synthetic"
SYN_CIK = "999999999"
SYN_ACCESSION = "0009999999-25-000001"


def pytest_collection_modifyitems(config, items):
    if os.environ.get("BDC_SOI_LIVE") != "1":
        skip = pytest.mark.skip(reason="live SEC test; set BDC_SOI_LIVE=1 and SEC_USER_AGENT to run")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip)


def stage_synthetic_package(cache_dir: Path, cik: str = SYN_CIK, accession: str = SYN_ACCESSION, primary: str = "syn-20250630.htm") -> FilingPackage:
    """Copy the synthetic package into a cache directory and write its manifest (no network)."""
    directory = cache_dir / "sec" / "filings" / cik / accession.replace("-", "")
    directory.mkdir(parents=True, exist_ok=True)
    files: list[PackageFile] = []
    for src in sorted((SYN / "package").iterdir()):
        dst = directory / src.name
        shutil.copy(src, dst)
        if src.name == "index.json":
            continue
        role = "primary" if src.name == primary else ("schema" if src.suffix == ".xsd" else ("linkbase" if src.name.endswith(("_lab.xml", "_pre.xml")) else ("xml" if src.suffix == ".xml" else "html")))
        files.append(PackageFile(name=src.name, url=f"synthetic://{src.name}", local_path=str(dst), size=dst.stat().st_size, sha256=sha256_of_file(dst), role=role, from_cache=True))
    sub_dir = cache_dir / "sec" / "submissions"
    sub_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(SYN / "submissions" / "CIK0999999999.json", sub_dir / "CIK0999999999.json")
    instance = choose_instance(files, primary)
    pkg = FilingPackage(cik, accession, directory, files, primary, instance, json.loads((directory / "index.json").read_text()))
    pkg.write_manifest()
    return pkg


@pytest.fixture
def app_config(tmp_path: Path) -> AppConfig:
    cfg = load_config(ROOT / "config" / "application.yml", {"paths.cache": str(tmp_path / "cache"), "paths.templates": str(ROOT / "templates"), "extraction.offline": True})
    cfg.sec.user_agent = None
    return cfg


@pytest.fixture
def registry() -> TemplateRegistry:
    reg = TemplateRegistry.from_directory(ROOT / "templates")
    reg.raise_if_invalid()
    return reg


@pytest.fixture
def synthetic_context(tmp_path: Path, app_config: AppConfig, registry: TemplateRegistry):
    from bdc_soi.pipeline import RunContext

    cache_dir = tmp_path / "cache"
    stage_synthetic_package(cache_dir)
    # Reuse the project's Arelle taxonomy cache so core XBRL schemas resolve offline.
    arelle_src = ROOT / "cache" / "arelle"
    if arelle_src.exists():
        shutil.copytree(arelle_src, cache_dir / "arelle", dirs_exist_ok=True)
    client = SecClient(app_config.sec, cache_dir, offline=True)
    return RunContext(config=app_config, registry=registry, client=client, cache_dir=cache_dir, offline=True)
