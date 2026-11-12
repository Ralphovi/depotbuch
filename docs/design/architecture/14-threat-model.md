---
created: 10.11.2026 19:03
type: architecture
status: living
tags:
  - architecture
  - security
  - threat-model
---
# 14. Threat model

> Living document. What is worth attacking, where the trust boundaries are, who the
> adversaries are, and which attacks depotbuch must withstand, each mapped to what
> mitigates it and the test that checks it. Open questions are marked **[OPEN]** inline.
>
> No product code exists yet. §14.1–§14.3 describe the design in proposal 0001; §14.4–§14.7
> grow as each boundary is built, and a PR that builds one fills in its rows.

## 14.1 Assets

| Asset | What losing it means |
|-------|----------------------|
| **Integrity of the figures** (activities, market data, derived results) | Wrong values, gains, taxes or returns that look right. The owner makes decisions on them, and the parallel run would pass or fail for the wrong reason. Silent corruption is **Critical** (the headline promise, §1.2). |
| **Confidentiality of the portfolio** (holdings, transactions, account numbers, balances, pension contracts, imported statement files, the HTML report, and the private test corpus of real statements on the developer's machine, proposal 0002) | A complete picture of the owner's wealth and banks: useful for fraud, phishing and social engineering. **High**. |
| **The login** (owner's credentials and sessions) | Full read access to the portfolio and the ability to change activities. **High**. |
| **Availability** | One user, no time pressure; statements and the database can be re-imported or restored. **Low**. |

The ratings above weigh each asset. A finding is rated on its own scale, the one in the
reviewer summary (`.oss-scanner/threat_model.md`, *How we rate severity*) and in issue
triage (ADR-0005, where Critical is `sev:critical` and High is `sev:major`):

| Finding | Rating |
|---------|--------|
| Silently wrong figures that look right; portfolio data readable, or code run, without authentication; a secret leaks (the Django secret key, the owner's credentials, a provider key) | Critical |
| Code execution or file access through a statement file or a price or FX response; portfolio data read with a stolen or forged session, or leaving the server other than through an export the owner asked for | High |
| Denial of service through a crafted input; CSV injection in an export | Medium |
| Needs the owner's own credentials or a deliberate misconfiguration | Low |

## 14.2 Trust boundaries

1. **Network → web front end and API.** Anything reaching the homelab's HTTPS endpoint. Only
   an authenticated owner may read or change data. TLS and login are required.

   What the scaffold (M0) exposes today, before any portfolio data exists:

   | Route | Login | Reveals |
   |-------|-------|---------|
   | `/api/health` | none | `{"status": "ok", "version": …}`, for the container's liveness probe |
   | `/api/openapi.json`, `/api/docs` | staff (admin login; anonymous requests redirect to it) | The API schema, and Swagger UI loading its script from a CDN |
   | `/admin/` | staff | Django admin; no models are registered yet |

   Settings come from `DEPOTBUCH_*` environment variables. `DEBUG` is off unless
   `DEPOTBUCH_DEBUG` is set, `ALLOWED_HOSTS` defaults to localhost, and without
   `DEPOTBUCH_SECRET_KEY` a random key is generated per process, so a missing key logs
   everyone out on restart rather than falling back to a known value.
2. **Statement files → adapters.** PDF, CSV and OFX files come from banks and brokers but
   pass through the owner's downloads folder; their content is untrusted and is parsed by
   ofxstatement plugins and depotbuch's OFX and CSV parsers.
3. **Price and FX providers → adapters.** Responses from Yahoo (through yfinance), ECB and
   later IBKR are third-party data over HTTPS.
4. **Installed packages → process.** ofxstatement, its plugins, yfinance, Django and the
   front-end libraries run with the server's full rights. Plugins are loaded from the
   owner's ofxstatement configuration.
5. **Server → exported files.** `depot report` and the CSV export write the full portfolio to
   a file that leaves the server's protection.

- **Pull requests from forks, in GitHub Actions.** A PR's code, title, body and branch name
  are attacker-controlled: anyone can open one. The checks run on `pull_request`, where the
  token is read-only and `actions/checkout` keeps no credentials, so PR-supplied code runs
  without write access. One workflow, `welcome-first-time-contributor.yml`, runs on
  `pull_request_target` instead, because a fork PR's `pull_request` token cannot comment;
  it holds `pull-requests: write` (its only permission) while handling a PR from anyone.
  That boundary holds only while the workflow neither checks the PR out nor interpolates
  the event payload into its script. It reads the author's login and the PR number through
  `context.payload` at run time and posts a fixed comment. The template checks both rules
  before the workflow ships (`test_pull_request_target_never_touches_pr_content` in its
  `template-test`): no `actions/checkout` step and no `${{ github.event` expression in a
  `pull_request_target` workflow. That test is not copied into this project, so a change
  to the workflow is reviewed by hand against the same two rules.

## 14.3 Adversaries

| Adversary | Can already |
|-----------|-------------|
| Anonymous network user | Reach the HTTPS endpoint if the homelab exposes it beyond the LAN or VPN. **[OPEN]** Exposure: LAN or VPN only, or the internet? |
| Crafted statement file | Get a file into the owner's import, for example a forged PDF or CSV by email. Runs no code by itself, but drives the parsers. |
| Compromised or malicious price source | Return wrong closes, splits or FX rates, or oversized responses. |
| Compromised dependency or plugin | Run code in the server process with access to the database. |
| Someone who obtains an export | Read the HTML report or CSV export if it is left on a shared device. |
| Fork PR author | As in §14.2. |

The owner is trusted; there are no other users.

## 14.4 STRIDE, per boundary

| Boundary | Threats that apply |
|----------|--------------------|
| 1 Network → web | **S**: guessed or stolen credentials, session theft. **T**: CSRF changing activities. **I**: data exposed without TLS or through an endpoint missing authentication. **D**: request floods (low impact). **E**: reaching the Django admin without staff rights. |
| 2 Statement files | **T**: rows that inject false activities, wrong ISINs or amounts. **D**: oversized or malformed files, XML entity expansion in OFX. **I**: CSV export cells that become spreadsheet formulas (CSV injection). |
| 3 Price and FX providers | **T**: wrong prices or splits silently change values. **D**: hanging or huge responses. |
| 4 Packages and plugins | **T**, **I**, **E**: arbitrary code in the server process. |
| 5 Exports | **I**: the full portfolio in a file. |

## 14.5 Attack catalog

| Attack | Mitigation (planned unless noted) |
|--------|-----------------------------------|
| Unauthenticated access to API or views | Every view and endpoint requires login; tested per endpoint (M6). |
| Credential stuffing or brute force | **[OPEN]** Rate limiting or lockout, decided in M6. |
| CSRF on changing endpoints | Django's CSRF protection for session-authenticated requests. |
| Plain-HTTP access | TLS required; secure cookies and HSTS in production settings. |
| Forged statement inserts activities | Every import reports added, skipped and rejected rows; oversold sales rejected; trade-to-cash matching surfaces unbalanced lines; the owner reviews the report. |
| XML entity expansion or external entities in OFX | Parse OFX with a hardened parser (no DTDs, no external entities). **[OPEN]** Which parser. |
| Oversized or malformed files | Size limits and parser errors become rejected rows, never crashes that lose the rest of the report. |
| CSV injection in the Parqet-format export | Escape cells that start with `=`, `+`, `-` or `@` where Parqet's import format allows it. **[OPEN]** Check what Parqet accepts. |
| Wrong prices from a provider | Splits and closes are visible in the holding detail; stale-data flags; provider chosen per security; manual override. **[OPEN]** A plausibility check on large day-to-day jumps. |
| Malicious dependency | Pinned dependencies, Dependabot with a 7-day cooldown, GPL-compatible packages from known sources; plugins come from the owner's own repositories. |
| Secrets in the repository | Secret scanning with push protection (repo settings); no real statements or data in fixtures. |

## 14.6 Abuse-case tests

None yet. Planned with the boundaries they test: malformed and oversized OFX, CSV and PDF
inputs; OFX with entity declarations; duplicate and overlapping imports; oversold sales;
API requests without a session or with a foreign CSRF token; export of cells starting with
formula characters.

## 14.7 Threat → test map

| Threat | Mitigation | Test |
|--------|------------|------|
| Silent duplicate activities | Identity = account + `FITID` | Gap until M2 |
| Cash line counted twice | Trade-to-cash matching | Gap until M1 (Hypothesis invariant) |
| Real statement data reaches the repository or a log | The private test corpus lives outside the repository and is passed only to its own session, `nox -s reconcile -- <path>`, never to the gate or CI, and only on trusted code (the owner's, an agent's in the owner's session that can already read the corpus, or code the owner has reviewed); the runner refuses a corpus or report path inside any clone or worktree of this repository or any Git worktree with a remote, and a symlinked report path, prints only synthetic case file names, field names and error kinds, and writes values to a report inside the corpus directory (proposal 0002) | `tests/testing/test_reconcile.py`, from M1 |
| Engine reaches Django or the network | Lint rule banning `django` and `ninja` in `engine/` and `adapters/`; a test that imports both packages without loading either framework. Network access is not checked yet. | Gate (ruff, `tests/test_boundaries.py`), from M0 |
| Unauthenticated API access | Staff login on the schema, docs and admin; only `/api/health` is open | `tests/web/test_api.py`, from M0; every data endpoint adds its own case from M6 |
| OFX entity expansion | Hardened parser | Gap until M5 |

## 14.8 Residual and accepted risks

- **Plugins and dependencies run with full rights.** depotbuch loads ofxstatement plugins
  in-process by design (one parser for all tools). Accepted because the plugins are the
  owner's own and installed deliberately; a sandbox is not planned. Accepted by the
  maintainer in proposal 0001's design.
- **Price data from an unofficial source.** yfinance has no integrity guarantee. Accepted
  for step 1; IBKR replaces it later.
- **Exports leave the server.** The owner is responsible for where the HTML report and CSV
  export go.

## 14.9 Gaps and their disposition

| Gap | Closed by |
|-----|-----------|
| No engine or adapter code yet, so no tests behind most of §14.5 | Each milestone in §9 adds the rows for the boundary it builds. |
| Deployment settings (`check --deploy`: HTTPS redirect, secure cookies, HSTS) not set | M6, with the container and TLS termination. |
| Network exposure and login hardening undecided | M6, with an update to this section. |
| OFX parser choice | M5. |
