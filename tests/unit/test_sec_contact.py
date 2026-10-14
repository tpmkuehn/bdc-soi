"""SEC contact resolution: --sec-email / --sec-organization, SEC_USER_AGENT fallback, failure before requests.

All tests are offline and use synthetic contacts (``@acme.test``); no real address is embedded anywhere.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import requests

from bdc_soi import ENGINE_VERSION
from bdc_soi.cli import _context, build_parser, main
from bdc_soi.config import (
    USER_AGENT_SETUP_MESSAGE,
    AppConfig,
    ContactEmailError,
    SecConfig,
    build_user_agent,
    is_genuine_user_agent,
    load_config,
    resolve_user_agent,
    validate_contact_email,
)
from bdc_soi.sec_client import SecClient, UserAgentError
from bdc_soi.xbrl_loader import TaxonomyUserAgentError, get_controller
from tests.conftest import ROOT

SYNTHETIC_EMAIL = "analyst@acme.test"
SYNTHETIC_ENV_UA = "Acme Research ops-team@acme.test"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Any attempt to open an HTTP connection fails the test."""

    def _refuse(*args, **kwargs):  # pragma: no cover - only hit on regression
        raise AssertionError("network access attempted during an offline test")

    monkeypatch.setattr(requests.Session, "request", _refuse)
    monkeypatch.setattr(requests, "get", _refuse)
    yield


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    monkeypatch.delenv("BDC_SOI_OFFLINE", raising=False)
    yield


# ---------------------------------------------------------------------------
# Explicit argument handling and validation
# ---------------------------------------------------------------------------


def test_build_user_agent_uses_application_name_version_and_email():
    assert build_user_agent(SYNTHETIC_EMAIL) == f"bdc_soi/{ENGINE_VERSION} {SYNTHETIC_EMAIL}"
    assert build_user_agent(SYNTHETIC_EMAIL, "Acme Research") == f"Acme Research bdc_soi/{ENGINE_VERSION} {SYNTHETIC_EMAIL}"
    assert build_user_agent("  analyst@acme.test ", "  Acme   Research ") == f"Acme Research bdc_soi/{ENGINE_VERSION} {SYNTHETIC_EMAIL}"
    assert is_genuine_user_agent(build_user_agent(SYNTHETIC_EMAIL))


@pytest.mark.parametrize(
    "bad",
    [None, "", "   ", "no-at-sign", "@acme.test", "analyst@", "analyst@acme", "two@at@acme.test", "analyst @acme.test", "<analyst@acme.test>", "analyst@acme.test\nX-Injected: 1", "Analyst Name analyst@acme.test"],
)
def test_validate_contact_email_rejects_empty_or_malformed(bad):
    with pytest.raises(ContactEmailError) as exc:
        validate_contact_email(bad)
    assert "--sec-email" in str(exc.value) and "SEC_USER_AGENT" in str(exc.value)


@pytest.mark.parametrize("placeholder", ["analyst@example.com", "your-monitored-email@acme.test", "monitored-mailbox@example.org"])
def test_validate_contact_email_rejects_documentation_placeholders(placeholder):
    with pytest.raises(ContactEmailError, match="placeholder"):
        validate_contact_email(placeholder)


def test_organization_requires_email_and_is_single_line():
    with pytest.raises(ContactEmailError, match="requires --sec-email"):
        resolve_user_agent(None, "Acme", env={"SEC_USER_AGENT": SYNTHETIC_ENV_UA})
    with pytest.raises(ContactEmailError):
        build_user_agent(SYNTHETIC_EMAIL, "   ")
    with pytest.raises(ContactEmailError):
        build_user_agent(SYNTHETIC_EMAIL, "Acme\x00Research")


# ---------------------------------------------------------------------------
# Precedence: explicit email > SEC_USER_AGENT > nothing (fail before requests)
# ---------------------------------------------------------------------------


def test_resolve_precedence_explicit_email_beats_environment():
    ua, source = resolve_user_agent(SYNTHETIC_EMAIL, None, env={"SEC_USER_AGENT": SYNTHETIC_ENV_UA})
    assert ua == f"bdc_soi/{ENGINE_VERSION} {SYNTHETIC_EMAIL}" and source == "cli"


def test_resolve_falls_back_to_environment_user_agent_as_given():
    assert resolve_user_agent(env={"SEC_USER_AGENT": "  " + SYNTHETIC_ENV_UA + " "}) == (SYNTHETIC_ENV_UA, "environment")


def test_resolve_without_any_contact_yields_none_not_a_default():
    assert resolve_user_agent(env={}) == (None, "none")
    assert resolve_user_agent(env={"SEC_USER_AGENT": "   "}) == (None, "none")


def test_explicit_empty_email_never_falls_back_to_environment():
    with pytest.raises(ContactEmailError):
        resolve_user_agent("", None, env={"SEC_USER_AGENT": SYNTHETIC_ENV_UA})
    with pytest.raises(ContactEmailError):
        resolve_user_agent("analyst@example.com", None, env={"SEC_USER_AGENT": SYNTHETIC_ENV_UA})


def test_load_config_environment_fallback_and_cli_override(monkeypatch, clean_env):
    cfg_path = ROOT / "config" / "application.yml"
    assert load_config(cfg_path).sec.user_agent is None and load_config(cfg_path).sec.user_agent_source == "none"
    monkeypatch.setenv("SEC_USER_AGENT", SYNTHETIC_ENV_UA)
    env_cfg = load_config(cfg_path)
    assert env_cfg.sec.user_agent == SYNTHETIC_ENV_UA and env_cfg.sec.user_agent_source == "environment"
    ua, source = resolve_user_agent(SYNTHETIC_EMAIL, "Acme", env={})
    cli_cfg = load_config(cfg_path, {"sec.user_agent": ua, "sec.user_agent_source": source})
    assert cli_cfg.sec.user_agent == ua and cli_cfg.sec.user_agent_source == "cli"
    # Provenance never changes the effective-configuration checksum, and the contact is excluded from it.
    assert env_cfg.checksum() == cli_cfg.checksum() == load_config(cfg_path).checksum()


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def _argv(command: str, tmp_path: Path, *extra: str) -> list[str]:
    base = {
        "extract": ["extract", "--cik", "999999999", "--output", str(tmp_path / "out")],
        "extract-universe": ["extract-universe", "--universe", str(ROOT / "config" / "bdc_universe.yml"), "--output", str(tmp_path / "out")],
        "inspect": ["inspect", "--cik", "999999999", "--output", str(tmp_path / "out")],
    }[command]
    return base + ["--cache", str(tmp_path / "cache"), "--templates", str(ROOT / "templates"), *extra]


def _args(command: str, *extra: str, tmp_path: Path):
    return build_parser().parse_args(_argv(command, tmp_path, *extra))


@pytest.mark.parametrize("command", ["extract", "extract-universe", "inspect"])
def test_cli_accepts_sec_email_and_organization_on_every_retrieval_command(command, tmp_path, monkeypatch, clean_env):
    monkeypatch.setenv("SEC_USER_AGENT", SYNTHETIC_ENV_UA)  # must lose to the explicit argument
    ctx = _context(_args(command, "--sec-email", SYNTHETIC_EMAIL, "--sec-organization", "Acme Research", tmp_path=tmp_path))
    expected = f"Acme Research bdc_soi/{ENGINE_VERSION} {SYNTHETIC_EMAIL}"
    assert ctx.client.config.user_agent == expected and ctx.config.sec.user_agent_source == "cli"
    assert ctx.client.session.headers["User-Agent"] == expected  # session built, no request made


@pytest.mark.parametrize("command", ["extract", "extract-universe", "inspect"])
def test_cli_falls_back_to_environment_user_agent(command, tmp_path, monkeypatch, clean_env):
    monkeypatch.setenv("SEC_USER_AGENT", SYNTHETIC_ENV_UA)
    ctx = _context(_args(command, tmp_path=tmp_path))
    assert ctx.client.config.user_agent == SYNTHETIC_ENV_UA and ctx.config.sec.user_agent_source == "environment"


@pytest.mark.parametrize("command", ["extract", "extract-universe", "inspect"])
def test_cli_live_run_without_contact_fails_before_any_request(command, tmp_path, clean_env, capsys):
    rc = main(_argv(command, tmp_path))
    err = capsys.readouterr().err
    assert rc == 2 and "--sec-email" in err and "SEC_USER_AGENT" in err and "--offline" in err
    assert not (tmp_path / "out").exists()  # failed before preparing output or touching the cache


@pytest.mark.parametrize("bad", ["", "not-an-email", "analyst@example.com"])
def test_cli_rejects_empty_or_malformed_explicit_email_even_with_environment(bad, tmp_path, monkeypatch, clean_env, capsys):
    monkeypatch.setenv("SEC_USER_AGENT", SYNTHETIC_ENV_UA)
    rc = main(_argv("extract", tmp_path, "--sec-email", bad))
    assert rc == 2 and "--sec-email" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_cli_organization_without_email_is_an_error(tmp_path, monkeypatch, clean_env, capsys):
    monkeypatch.setenv("SEC_USER_AGENT", SYNTHETIC_ENV_UA)
    assert main(_argv("extract", tmp_path, "--sec-organization", "Acme")) == 2
    assert "requires --sec-email" in capsys.readouterr().err


def test_offline_context_needs_no_contact(tmp_path, clean_env):
    ctx = _context(_args("extract", "--offline", tmp_path=tmp_path))
    assert ctx.offline and ctx.client.config.user_agent is None and ctx.config.sec.user_agent_source == "none"
    with pytest.raises(UserAgentError):
        _ = ctx.client.session  # offline runs never build a live session


@pytest.mark.parametrize("argv", [["--help"], ["extract", "--help"], ["extract-universe", "--help"], ["inspect", "--help"], ["validate-templates", "--help"]])
def test_help_needs_no_contact(argv, clean_env, capsys):
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 0
    out = capsys.readouterr().out
    if argv[0] in {"extract", "extract-universe", "inspect"}:
        assert "--sec-email" in out and "--sec-organization" in out


def test_non_sec_commands_need_no_contact(tmp_path, clean_env):
    assert main(["validate-templates", "--templates", str(ROOT / "templates"), "--schema", str(ROOT / "config" / "template.schema.json")]) == 0


# ---------------------------------------------------------------------------
# Consistent propagation across retrieval paths
# ---------------------------------------------------------------------------


def test_sec_client_session_carries_resolved_user_agent(tmp_path):
    ua = build_user_agent(SYNTHETIC_EMAIL, "Acme")
    client = SecClient(SecConfig(user_agent=ua), tmp_path)
    assert client.session.headers["User-Agent"] == ua


def test_sec_client_refuses_live_session_without_contact(tmp_path):
    with pytest.raises(UserAgentError) as exc:
        _ = SecClient(SecConfig(user_agent=None), tmp_path).session
    assert str(exc.value) == USER_AGENT_SETUP_MESSAGE


def test_arelle_web_cache_uses_the_same_user_agent_online(tmp_path):
    ua = build_user_agent(SYNTHETIC_EMAIL, "Acme")
    cntlr = get_controller(tmp_path / "cache", offline=False, user_agent=ua)
    assert cntlr.webCache.httpUserAgent == ua and cntlr.webCache.workOffline is False
    # A later offline call on the shared controller drops the contact instead of keeping it around.
    cntlr = get_controller(tmp_path / "cache", offline=True, user_agent=None)
    assert ua not in cntlr.webCache.httpUserAgent and cntlr.webCache.workOffline is True


def test_arelle_online_without_contact_fails_before_requests(tmp_path):
    with pytest.raises(TaxonomyUserAgentError, match="--sec-email"):
        get_controller(tmp_path / "cache", offline=False, user_agent=None)
    with pytest.raises(TaxonomyUserAgentError):
        get_controller(tmp_path / "cache", offline=False, user_agent="Organization monitored-mailbox@example.com")


# ---------------------------------------------------------------------------
# No personal or placeholder contact default in runtime configuration
# ---------------------------------------------------------------------------

_EMAIL_IN_TEXT = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def test_no_contact_default_in_models_or_tracked_runtime_configuration():
    assert SecConfig().user_agent is None and AppConfig().sec.user_agent is None
    runtime_files = sorted((ROOT / "src" / "bdc_soi").glob("*.py")) + sorted((ROOT / "config").glob("*.yml"))
    assert runtime_files
    found = {str(p.relative_to(ROOT)): _EMAIL_IN_TEXT.findall(p.read_text(encoding="utf-8")) for p in runtime_files}
    assert not {k: v for k, v in found.items() if v}, "email addresses embedded in runtime code or configuration"


def test_env_example_and_readme_use_placeholders_only():
    for name in (".env.example", "README.md"):
        for email in _EMAIL_IN_TEXT.findall((ROOT / name).read_text(encoding="utf-8")):
            assert email.lower().endswith(("@example.com", "@example.org", "@your-domain")), f"{name}: unexpected contact {email}"
            assert not is_genuine_user_agent(f"Org {email}")
