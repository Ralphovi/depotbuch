# Threat model: depotbuch

Reviewer-facing summary of what an attacker can reach and how bad each outcome is, for
security reviewers and scanners. The full, living threat model is
[architecture §14](../docs/design/architecture/14-threat-model.md). Where this file and §14
differ about what exists in code today, this file describes the code and §14 describes the
design it is growing into. A change that adds an untrusted input or moves a trust boundary
updates both in the same PR.

## What this project does

depotbuch is a single-user, self-hosted portfolio tracker. The owner imports bank and broker
statements (PDF, CSV, OFX) through ofxstatement plugins, OFX files or a Parqet CSV export.
Adapters turn them into activities; a pure-Python engine computes holdings, lots, values,
taxes and returns from those activities plus prices (yfinance) and FX rates (ECB). A Django
backend stores the data and serves a JSON API (Django Ninja) to a TypeScript front end; a
`depot` CLI runs the same engine as Django management commands. It runs as one container on
the owner's homelab, behind TLS and a login.

Today the repository holds the project scaffold only; the components above are being built
(architecture §9).

## Where untrusted input enters

Treat all of the following as attacker-controlled:

1. **Statement files** given to `depot import`: content parsed by ofxstatement plugins and by
   depotbuch's OFX and Parqet CSV parsers (`src/depotbuch/adapters/`).
2. **Price and FX responses** from Yahoo Finance (via yfinance) and the ECB, fetched by
   `depot update` (`src/depotbuch/adapters/`).
3. **HTTP requests** to the web front end and the API under `/api/` (`src/depotbuch/web/`),
   from anyone who can reach the server.
   Today only `/api/health` answers without a login (status and version). The API schema
   and Swagger UI (`/api/openapi.json`, `/api/docs`) and `/admin/` need a staff login.

Trusted: the owner (the only user), the ofxstatement plugins the owner installs, the server's
configuration, and the database.

Already in place from the template: `.github/workflows/welcome-first-time-contributor.yml`
runs on `pull_request_target`, so it holds a token with `pull-requests: write` (its only
permission) while handling a pull request from any fork. The PR's code, title, body and
branch name are attacker-controlled. The workflow never checks the PR out and never
interpolates the event payload into its script; it reads only the author's login and the
PR number from the payload and posts a fixed comment. A change that adds an
`actions/checkout` step or a `${{ github.event` expression to that workflow is in scope.

## What must hold

- No figure is silently wrong: an import never drops a row without reporting it, never counts
  a cash movement twice, and never stores a sale larger than the holding.
- No data is readable or changeable without an authenticated session; nothing is served over
  plain HTTP.
- No input file or provider response can execute code, read files or exhaust the server
  (for example through XML entity expansion in OFX).
- The engine and adapters never import Django.
- Real statement data never enters the repository, CI or a test log. The private test
  corpus (proposal 0002) lives outside the repository, is named only by
  `DEPOTBUCH_PRIVATE_CORPUS` (a path inside the checkout is refused), and its runner prints
  nothing taken from a case file.

## Components that matter most

In order: the web project and API (`src/depotbuch/web/`), the import adapters
(`src/depotbuch/adapters/`), the portfolio app's import and identity logic
(`src/depotbuch/web/portfolio/`), the engine (`src/depotbuch/engine/`).

Lower priority: the CLI, the HTML report, test tools, build automation.

Out of scope: generated code (the front end's API client); third-party code (report a
dependency bug only if this project's use of it is what makes it exploitable).

## Known gaps: do not report these on their own

- ofxstatement plugins run in-process with full rights, by design. A way for a *statement
  file* to make a plugin run code is still in scope.
- yfinance data has no integrity guarantee. Missing plausibility checks on prices are known;
  a way for a response to corrupt unrelated data is in scope.
- Rate limiting on login is not decided yet (§14.5).
- Production settings (HTTPS redirect, secure cookies, HSTS) arrive with the deployment
  milestone; the scaffold runs with Django's defaults behind `DEPOTBUCH_*` variables.

## How to exercise it

`nox -s gate` runs every check (lint, types, tests, docs). Run the server locally with the
Django development server against a SQLite database and drive the inputs with
`depot import FILE` and requests to `/api/`. Use synthetic data only.

## How we rate severity

- **Critical:** silently wrong figures that look right; remote access to portfolio data
  or code execution without authentication; a leaked secret (the Django secret key, the
  owner's credentials, a provider key).
- **High:** code execution or file access through a statement file or provider response;
  reading the portfolio with a stolen or forged session, or portfolio data leaving the
  server other than through an export the owner asked for.
- **Medium:** denial of service through a crafted input; CSV injection in an export.
- **Low:** issues needing the owner's own credentials or a deliberate misconfiguration.

The same scale is in architecture §14.1 and in issue triage (ADR-0005).

A clean reproducer matters more than a severity label. The best form is a failing test in
the style of the existing ones.
