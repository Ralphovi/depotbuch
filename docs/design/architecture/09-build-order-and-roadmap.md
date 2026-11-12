---
created: 10.11.2026 19:03
type: architecture
status: living
tags:
  - architecture
---
# 9. Build order and roadmap

> Living document. Derived from proposal 0001 (the product spec, PR #3). There is no
> implementation-arc proposal yet; when one is written it becomes the authoritative plan and
> this section summarizes it. Milestone plans are proposals of their own: M1's is
> [proposal 0002](../proposals/draft/0002-m1-engine-core.md). GitHub milestones should carry the same names. Open questions
> are marked **[OPEN]** inline.

## The order

| # | Milestone | What it proves | Done when |
|---|-----------|----------------|-----------|
| M0 | Scaffold | The package layout and the gate work. | `nox -s gate` passes locally and in CI on Python 3.11–3.14; the engine-without-Django rule is enforced. |
| M1 | Engine core | The numbers can be right before any data exists. | Lots (FIFO), valuation per asset type, Festgeld accrual, trade-to-cash matching, TTWROR, IZF and tax attribution pass hand-computed cases, every case in default and `--parqet` mode, plus Hypothesis invariants (lots sum to holdings, no cash line counted twice, TTWROR independent of how a range is split); a local-only reconciliation against a real broker history matches its holdings statements, position values, distributions and sale gains (proposal 0002). |
| M2 | Parqet CSV import | The existing history can come in, and identity and reporting hold. | The real export imports with every row reported as added, skipped or rejected; re-import adds nothing; oversold sales are rejected. |
| M3 | Market data | Securities are valued from real closes and FX. | `depot update` fetches yfinance closes and splits and ECB rates incrementally through the provider interface; manual CSV works; stale data is flagged; reports work offline. |
| M4 | Storage and CLI views | The seven views exist end to end. | `depot providers`, `dashboard`, `holdings`, `holding`, `lots`, `income`, `activities` and `report` run on the imported history, with all filters and `--json`, under 2 s for 10 years and 100 assets. |
| M5 | Statements in | New activity flows in without manual entry (goal G6). | OFX and in-process plugin imports work; deposits are classified by account configuration; trades are matched to cash lines; the plugins emit `invest_lines` (work in the plugin repositories). |
| M6 | Web API and front end | The views are reachable from desktop and phone. | Ninja API with OpenAPI behind login and TLS; TypeScript front end with the seven views and charts, starting from a design proposal; container deployed on the homelab. |
| M7 | Parallel run (step 1 done) | depotbuch can replace Parqet. | One month in which `--parqet` figures agree with Parqet within the §10 tolerances, every difference explained by an open question or fixed; Parqet cancelled. |
| M8 | Pension contracts (step 2) | Riester, Rürup and bAV fit the same model. | Contributions, allowances, employer share and contract valuations (`depot valuation add`) appear in the same portfolio and figures. |

M2 can start as soon as the engine's activity type is settled; M5's plugin work runs in
other repositories and can proceed in parallel with M3 and M4.

**[OPEN]** Plugin work order: Scalable first (memo already carries units and ISIN), then
Consorsbank trade confirmations, then Revolut trading statements?

## Where to start contributing

- Hand-computed test cases for a calculation rule (§8.2–§8.5): small, self-contained and the
  most valuable thing for goal 1.
- Engine functions behind those cases, in plain Python with no Django.
- Parser fixtures with synthetic data (never real statements).

## Later

- Interactive Brokers as primary price source (one month of exchange subscriptions to
  backfill, then the free previous-day close). **[OPEN]** What IBKR charges for German
  Level 1 data, and how many years of daily history one month returns.
- FinTS adapter.
- Realized-gain methods LIFO and average.
- Drawdown chart, returns heatmap, trades view, benchmark comparison, capital view.
- PostgreSQL as a tested option.
