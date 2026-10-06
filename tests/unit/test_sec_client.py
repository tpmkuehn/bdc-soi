from pathlib import Path

import pytest

from bdc_soi.config import SecConfig, is_genuine_user_agent
from bdc_soi.sec_client import (
    OfflineCacheMiss,
    RateLimiter,
    SecClient,
    SecClientError,
    UserAgentError,
    accession_file_url,
    accession_index_url,
    accession_nodash,
    is_illustrative_accession,
    normalize_accession,
    normalize_cik,
    pad_cik,
    submissions_url,
)


def test_cik_normalization():
    assert normalize_cik("0001837532") == "1837532"
    assert normalize_cik(1837532) == "1837532"
    assert pad_cik("1837532") == "0001837532"
    assert normalize_cik("0") == "0"
    with pytest.raises(ValueError):
        normalize_cik("abc")


def test_accession_forms():
    assert normalize_accession("000119312526341358") == "0001193125-26-341358"
    assert accession_nodash("0001193125-26-341358") == "000119312526341358"
    assert is_illustrative_accession("0000000000-26-000001")
    assert not is_illustrative_accession("0001193125-26-341358")


def test_url_construction():
    assert submissions_url("1837532") == "https://data.sec.gov/submissions/CIK0001837532.json"
    assert accession_index_url("1837532", "0001193125-26-341358") == "https://www.sec.gov/Archives/edgar/data/1837532/000119312526341358/index.json"
    assert accession_file_url("1837532", "0001193125-26-341358", "a.htm").endswith("/000119312526341358/a.htm")


def test_user_agent_rules():
    assert not is_genuine_user_agent(None)
    assert not is_genuine_user_agent("Organization monitored-mailbox@example.com")
    assert not is_genuine_user_agent("Your Organization your-monitored-email@example.com")
    assert not is_genuine_user_agent("no-email-here")
    assert is_genuine_user_agent("Acme Research ops-team@acme-research.org")


def test_rate_limiter_enforces_interval():
    sleeps: list[float] = []
    clock = [0.0]
    lim = RateLimiter(0.2)
    lim.wait(sleep=sleeps.append, now=lambda: clock[0])
    lim.wait(sleep=sleeps.append, now=lambda: clock[0])
    assert sleeps and abs(sleeps[0] - 0.2) < 1e-9


class _Resp:
    def __init__(self, status, content=b"", headers=None):
        self.status_code = status
        self.content = content
        self.headers = headers or {}


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, url, timeout):
        self.calls += 1
        return self.responses.pop(0)


def test_retries_on_503_then_success(tmp_path: Path):
    session = _Session([_Resp(503), _Resp(429, headers={"Retry-After": "1"}), _Resp(200, b"ok")])
    sleeps: list[float] = []
    client = SecClient(SecConfig(user_agent="Acme ops@acme.test", retries=4, request_delay_seconds=0.1), tmp_path, session=session, sleep=sleeps.append)
    res = client.fetch_to_cache("https://example.test/x.json", tmp_path / "x.json")
    assert res.local_path.read_bytes() == b"ok" and session.calls == 3 and not res.from_cache
    assert len(client.request_log) == 2 and all("User-Agent" not in str(e) for e in client.request_log)
    # second fetch reuses the cache
    res2 = client.fetch_to_cache("https://example.test/x.json", tmp_path / "x.json")
    assert res2.from_cache and session.calls == 3


def test_gives_up_after_bounded_retries(tmp_path: Path):
    session = _Session([_Resp(500)] * 3)
    client = SecClient(SecConfig(user_agent="Acme ops@acme.test", retries=2, request_delay_seconds=0.1), tmp_path, session=session, sleep=lambda s: None)
    with pytest.raises(SecClientError):
        client.get_bytes("https://example.test/y")
    assert session.calls == 3


def test_non_retryable_404_fails_fast(tmp_path: Path):
    session = _Session([_Resp(404)])
    client = SecClient(SecConfig(user_agent="Acme ops@acme.test", retries=4, request_delay_seconds=0.1), tmp_path, session=session, sleep=lambda s: None)
    with pytest.raises(SecClientError):
        client.get_bytes("https://example.test/z")
    assert session.calls == 1


def test_offline_mode_refuses_network(tmp_path: Path):
    client = SecClient(SecConfig(user_agent="Acme ops@acme.test"), tmp_path, offline=True)
    with pytest.raises(OfflineCacheMiss):
        client.fetch_to_cache("https://example.test/a", tmp_path / "a")


def test_example_user_agent_blocks_live_session(tmp_path: Path):
    client = SecClient(SecConfig(user_agent="Organization monitored-mailbox@example.com"), tmp_path)
    with pytest.raises(UserAgentError):
        _ = client.session
