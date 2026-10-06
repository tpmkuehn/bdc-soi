"""Live SEC integration tests (SPEC 22.3). Skipped unless BDC_SOI_LIVE=1 and a genuine SEC_USER_AGENT is set."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from bdc_soi.config import is_genuine_user_agent, load_config
from bdc_soi.output import write_run
from bdc_soi.pipeline import RunContext, process_filing
from bdc_soi.sec_client import SecClient
from bdc_soi.templates import TemplateRegistry
from tests.conftest import ROOT

LIVE_CIK = os.environ.get("BDC_SOI_LIVE_CIK", "1837532")  # Apollo Debt Solutions BDC (verified via SEC submissions, 2026-10-06)
LIVE_ACCESSION = os.environ.get("BDC_SOI_LIVE_ACCESSION", "0001193125-26-341358")

pytestmark = pytest.mark.live


@pytest.mark.skipif(not is_genuine_user_agent(os.environ.get("SEC_USER_AGENT")), reason="SEC_USER_AGENT not set to a genuine contact")
def test_retrieve_extract_and_rerun_from_cache(tmp_path: Path):
    cfg = load_config(ROOT / "config" / "application.yml", {"paths.cache": str(ROOT / "cache")})
    reg = TemplateRegistry.from_directory(ROOT / "templates")
    reg.raise_if_invalid()
    cache = ROOT / "cache"
    ctx = RunContext(config=cfg, registry=reg, client=SecClient(cfg.sec, cache), cache_dir=cache, offline=False)
    r1 = process_filing(ctx, LIVE_CIK, LIVE_ACCESSION)
    assert r1.diagnostic.status != "failed" and r1.holdings and r1.package is not None
    out1 = tmp_path / "live1"
    write_run(ctx, [r1], out1, started=datetime.now(timezone.utc), run_id="live1", command="extract")
    # Rerun entirely offline from cache.
    ctx_off = RunContext(config=cfg, registry=reg, client=SecClient(cfg.sec, cache, offline=True), cache_dir=cache, offline=True)
    r2 = process_filing(ctx_off, LIVE_CIK, LIVE_ACCESSION)
    out2 = tmp_path / "live2"
    write_run(ctx_off, [r2], out2, started=datetime.now(timezone.utc), run_id="live2", command="extract")
    for name in ("holdings.csv", "validation.csv", "long_xbrl_facts.parquet", "matching_diagnostics.csv"):
        assert hashlib.sha256((out1 / name).read_bytes()).hexdigest() == hashlib.sha256((out2 / name).read_bytes()).hexdigest(), name
    assert all(f.from_cache for f in r2.package.files)
