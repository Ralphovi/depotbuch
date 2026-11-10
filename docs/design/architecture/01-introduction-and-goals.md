---
created: 10.11.2026 19:03
type: architecture
status: living
tags:
  - architecture
---
# 1. Introduction and goals

> Living document. What depotbuch is and why. Open questions are marked **[OPEN]** inline.

## 1.1 What this is

depotbuch is a self-hosted portfolio tracker. It shows every asset with every provider in
one portfolio, and each provider on its own. The providers today are Consorsbank, Revolut,
Scalable and the banks that hold deposits. Assets include securities, broker cash accounts
(Verrechnungskonto), Tagesgeld, Festgeld and, in step 2, pension contracts. All performance
figures are computed in EUR and net of taxes. Bank and broker statements come in through
ofxstatement, which also feeds GnuCash and Autobook, and depotbuch turns them into
Parqet-style views: dashboard, holdings, lots, income and activities. It replaces Parqet's
paid Plus tier; the product spec is proposal 0001 (PR #3).

The project is finished when Parqet can be cancelled. That takes one parallel-run month in
which depotbuch, run in Parqet-compatible mode, agrees with Parqet within the tolerances in
§10.

## 1.2 The headline promise

**The numbers are right and reproducible.** Every figure (value, invested capital, realized
gain, income, taxes, TTWROR, IZF) is recomputed from the stored activities plus market data.
It can be reproduced from the database and an as-of date, and it is the same in the CLI, the
API and the web front end. An import never drops a row silently and never counts a cash
movement twice. A wrong number that goes unnoticed is the worst outcome; the threat model
(§14) rates silently corrupting results as Critical.

## 1.3 Quality goals

| # | Goal | What it means here |
|---|------|--------------------|
| 1 | Correctness | Figures match hand-computed cases to the cent and Parqet within the acceptance tolerances (§10). No double counting, no silent drops. |
| 2 | Reproducibility | Activities are the only stored fact about a position. Every report can be rebuilt from the database and an as-of date, and imports are idempotent. |
| 3 | Privacy and confidentiality | Financial data stays on the homelab, behind a login and TLS. The only outbound calls go to the configured price and FX providers. |
| 4 | Low effort to run | No manual data entry in the normal flow: statements in, reports out. |
| 5 | Performance | Reports for 10 years of history and 100 assets finish in under 2 s. |
| 6 | Reusability | The engine has no framework dependency, so Autobook can take it over without changing its inputs. |

When goals conflict, the lower number wins.

## 1.4 Stakeholders and target users

| Who | Role |
|-----|------|
| The owner (one private investor) | The only user: imports statements, reads the views on desktop and phone, runs the parallel run against Parqet. Also the maintainer. |
| Coding agents | Build to the design under the rules in `AGENTS.md`; the maintainer reviews and merges. |
| Autobook | A sibling project that reads the same ofxstatement output and may later adopt the engine. |
| ofxstatement plugin authors | The Consorsbank, Scalable and Revolut plugins (same maintainer) must emit investment lines (§3.2). |

There is a single user per installation; multi-user support is a non-goal.

## 1.5 Scope boundaries

**In scope, step 1.** One portfolio across all providers in EUR, with every view also
filtered to a single provider, account, asset class or asset. Asset classes: securities
(stocks, ETFs, funds), broker cash accounts, Tagesgeld, Festgeld with daily accrued interest,
and other assets with a known value. YTD and range performance with dividends and interest
included and taxes deducted; income per year, net, with withheld tax shown separately;
per-position and per-lot performance including IZF. Imports from ofxstatement plugins, OFX
files and the Parqet CSV export, plus manual entry. Seven views (§5.3) in a CLI, a JSON API
and a web front end, and a static HTML report.

**In scope, step 2.** Pension contracts (Riester, Rürup, bAV) with contributions, allowances
and contract value, inside the same portfolio and figures.

**Non-goals.**

- Autosync or broker APIs. Fetching statements stays out of scope, as it does for Autobook.
- X-Ray, weighting by sector, region or country, dividend forecast and calendar, tax
  reports.
- Watchlists, sharing, multi-user, mobile apps, real estate, crypto, P2P.

**[OPEN]** What counts as "other" assets in step 1, beyond broker cash, Tagesgeld and
Festgeld?
