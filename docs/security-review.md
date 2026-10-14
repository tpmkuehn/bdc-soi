# Repository security review (2026-10-14)

Scope and method; findings are reported without reproducing any value.

## Scope
- Repository: `https://github.com/tpmkuehn/bdc-soi.git` (origin verified), branch `main`, upstream `origin/main`.
- History: full (not shallow), one reachable commit on `main`; no other local or remote branches, no tags.
- Working tree: clean at review start (no staged or unstaged changes).
- Tracked content: 174 files (source, configuration, scripts, tests, synthetic fixtures, templates, golden
  manifests, documentation). No notebooks or binary files are tracked.
- Ignored content (`.venv/`, `cache/`, `output/`, `.env*`, logs, `golden/annotations/`, caches) was deliberately
  not opened or scanned.

## Tools
- gitleaks 8.30.1: `gitleaks git --redact=100` over the history and `gitleaks dir --redact=100` over a `git archive`
  export of the tracked tree (so ignored directories were excluded).
- Manual review: regular-expression sweeps for email addresses, API keys, tokens, bearer/authorization headers,
  private-key blocks, credential-bearing URLs, cloud signatures and connection strings; review of `.gitignore` and
  tracked filenames; review of the SEC client, configuration loader, Arelle loader and CLI.

## Findings
| # | Type | Location | Assessment |
| --- | --- | --- | --- |
| 1 | gitleaks `generic-api-key` | `tests/fixtures/synthetic/README.md` line 10, commit `1ddb62e` | False positive: an 8-character date fragment inside a synthetic fixture filename. |
| 2 | Contact emails | `.env.example`, `README.md`, `SPEC.md`, tests | Documentation placeholders (`example.com`, `your-domain`) and synthetic test contacts (`acme.test`); not genuine. |
| 3 | Git author metadata | commit `1ddb62e` | The author name and email in the commit metadata are the project owner's; this is attribution, not a credential, and was left unchanged. |
| 4 | Arelle default User-Agent | `src/bdc_soi/xbrl_loader.py` | SEC-hosted taxonomy downloads used Arelle's built-in User-Agent instead of the project's monitored contact. Fixed (D48). |

No API keys, access tokens, passwords, private keys, signed URLs, connection strings or embedded authentication
headers were found in the tracked tree or in the reachable history. No personal contact address was found in
tracked runtime code or configuration; `config/application.yml` ships `user_agent: null`.

## Unresolved historical exposure
None identified. Nothing requires revocation or rotation based on this review.

## Limitations
- Scanners detect known patterns; a secret of an unrecognised format could be missed.
- Only the reachable history on `origin` was reviewed; forks, clones or previously force-pushed objects are
  outside this review.
- Ignored local files were not inspected by design.
