---
created: 10.11.2026 19:04
type: proposal
status: draft
author: Eduard Ralph
tracking-issue: https://github.com/Ralphovi/depotbuch/issues/1
supersedes:
tags:
  - proposal
---
# Proposal: depotbuch product spec (Parqet replacement)

Taken from the product spec of 9 November 2026, reordered to follow the proposal template.
One correction since: under *Calculations*, income that stays inside the selected slice and
taxes on sales are each counted once (the spec counted both twice).

## Motivation

### Purpose and scope

depotbuch shows all assets across all providers in one portfolio, and each provider on its own. That aggregation is the core feature: Parqet's free tier allows one portfolio and 5 additional assets, so only the paid tier (Plus: 11.99 € a month as of September 2026) covers it. Performance is always net of taxes.

**Step 1 goals**

- G1 — One portfolio across all providers (Consorsbank, Revolut, Scalable and the banks holding deposits), in EUR. Every view also works for a single provider.
- G2 — Asset classes: securities (stocks, ETFs, funds), broker cash accounts (Verrechnungskonto), Tagesgeld, Festgeld with daily accrued interest, and other assets with a known value.
- G3 — YTD performance per asset, per provider and in total, with dividends and interest included and taxes deducted.
- G4 — Dividends and interest per year, net, with withheld tax shown separately.
- G5 — Per-position and per-lot performance since the buy date, including IZF.
- G6 — No manual data entry in the normal flow: statements in, reports out.

**Step 2 goals**

- G7 — Pension contracts: Riester, Rürup and bAV, with contributions, allowances and the contract value, inside the same portfolio and performance figures.

**Non-goals**

- Autosync or broker APIs. Fetching statements stays out of scope, as it does for Autobook.
- X-Ray, weighting by sector, region or country, dividend forecast and calendar, tax reports.
- Watchlists, sharing, multi-user, mobile apps, real estate, crypto, P2P.

**Done when** Parqet can be cancelled: one parallel-run month in which depotbuch, in Parqet-compatible mode, agrees with Parqet within the tolerances in *Acceptance*.

depotbuch is its own project, separate from Autobook. It reads the same ofxstatement output, and its engine has no framework dependency, so Autobook can take it over later without changing its inputs.

### Parqet reference and scope

Step 1 covers Parqet's dashboard, position list, returns and dividend views across every provider, plus Tagesgeld and Festgeld. It skips Parqet's analysis and tax modules. The feature list follows [finanzwissen.de's Parqet test](https://finanzwissen.de/erfahrungen/parqet) (as of September 2026) and Parqet's own [TTWROR article](https://parqet.com/en/blog/true-time-weighted-rate-of-return) and [FAQ on the calculation](https://faq.parqet.com/article/115-performancevergleich).

| Parqet feature | Parqet tier | depotbuch |
| --- | --- | --- |
| Several portfolios or depots in one view | Plus (5), Investor (15) | Step 1: all providers in one portfolio, each also on its own |
| Additional assets (deposits, pensions, real estate) | Basis: 5, Plus: unlimited | Step 1: Tagesgeld, Festgeld; step 2: Riester, Rürup, bAV |
| Dashboard: value, invested capital, price gain, dividends, realized gains, allocation donut | Basis | Step 1 |
| Chart switch: value, performance, drawdown, dividends | Basis | Step 1 (drawdown later) |
| Filters: sub-depot, asset class, time range | Basis | Step 1: provider, account, asset class, time range |
| Position list: price gain, dividends, realized gain, weight | Basis | Step 1 |
| IZF and TTWROR, per portfolio and per holding | Basis | Step 1, net of taxes |
| TTWROR performance chart | Plus | Step 1 |
| Activities list, manual entry, CSV export | Basis | Step 1 |
| PDF/CSV import for 58 banks, autosync | Basis | Step 1 via ofxstatement; no autosync |
| Realized-gain method: FIFO, LIFO or average | Basis | Step 1 FIFO; others later |
| Dividend dashboard: monthly, per year, accumulated, per security | Basis | Step 1, with interest added |
| Returns heatmap, trades view, benchmark comparison, capital view | Plus | Later |
| Weighting by sector, region, country, currency; X-Ray | Plus | Out |
| Tax dashboard, withholding tax per country | Plus | Out (taxes shown per activity and per range) |
| Dividend forecast and calendar, fees view, watchlists, sharing | mixed | Out |

## Design

### Domain model

The activity is the only fact depotbuch stores about a position; holdings, lots, values and every report are recomputed from activities plus market data. That keeps re-imports, corrections and method changes (FIFO to average, say) free of migrations.

> The domain-model diagram (6 stored entities, 3 derived) in the original document did not
> survive the Markdown export. It is still to be redrawn here as Mermaid.

One portfolio holds all providers; a provider holds accounts (a depot, a Tagesgeld account, each Festgeld deposit); an account holds activities, and each activity refers to one asset. A position is an asset across accounts. Filtering by provider or account narrows every view. In step 2, a pension contract is one more account whose asset is the contract, valued from its statements.

### Data ingestion

All broker data enters through ofxstatement, so a statement is parsed one way for both GnuCash and depotbuch. Parqet's CSV export is a one-time migration path for the existing history.

**Import paths**

1. **ofxstatement plugin, in-process.** `depot import -t <section> <file>` loads the plugin from the user's ofxstatement config. It renders the statement with ofxstatement's own `OfxWriter`, then parses that OFX. PDFs work whenever the plugin reads them.
2. **OFX file.** XML or SGML OFX with an investment statement (`INVSTMTRS`).
3. **Parqet CSV export.** Semicolon-separated, header-driven. Buy, Sell, Dividend, Interest, TransferIn and TransferOut are imported; cash-only rows are skipped and counted.
4. **Manual entry.** `depot add` for anything without a statement, with the same fields as an imported activity.

**Mapping**

| Activity | OFX element | Units | Cash (settlement currency) |
| --- | --- | --- | --- |
| Buy | `BUYSTOCK`, `BUYMF`, `BUYDEBT` | + | negative: price × units + fees + taxes |
| Sell | `SELLSTOCK`, `SELLMF`, `SELLDEBT` | − | positive: price × units − fees − taxes |
| Dividend, distribution, coupon | `INCOME` | 0 | net amount credited; `WITHHOLDING` kept as withheld tax |
| Reinvested dividend | `REINVEST` | + | split into a dividend and a buy |
| Delivery in or out | `TRANSFER` | ± | none; valued at the stated cost basis |
| Security expense | `INVEXPENSE` | 0 | negative |
| Split | `SPLIT` | ratio | none |

**Deposits and contracts.** Tagesgeld and Festgeld come from the same ofxstatement plugins, as ordinary bank lines (`statement.lines`); each bank account is configured once with its asset type. Pension contracts arrive as yearly statements, mostly PDFs without a plugin.

| Activity | Source | Cash effect |
| --- | --- | --- |
| Tagesgeld deposit / withdrawal | bank line `XFER`, `DEP`, `DEBIT` | inflow / outflow of the account |
| Interest credited | bank line `INT` | income, net; tax withheld recorded separately |
| Festgeld placement | bank line, tagged by configuration | inflow; principal, rate, start and maturity entered once |
| Festgeld maturity | bank line | outflow of principal; interest as income |
| Pension contribution, allowance (Zulage), employer share (step 2) | yearly statement or bank line | inflow |
| Pension contract value (step 2) | yearly statement, `depot valuation add` | valuation on that date |

Whether a bank line is a transfer between own accounts or an external flow is decided by the account configuration, not guessed per line.

**Rules**

- An activity's identity is account plus `FITID`. Re-importing the same file adds nothing. Parqet rows have no ID, so the ID is a hash of the row.
- The security key is the ISIN. A plugin that emits a ticker or WKN instead is mapped to an ISIN once and remembered.
- The account is `BROKERID:ACCTID` from the statement and can be overridden per import.
- Each import reports added, skipped and rejected rows. Nothing is dropped silently.
- A sale larger than the holding is rejected with the date and the missing units, because it means earlier activities are missing.

**Contract for ofxstatement plugins.** Depot statements must fill `statement.invest_lines` (ofxstatement 0.9 or later), not `statement.lines`. `security_id` must be the ISIN, and `statement.currency` must be the settlement currency. None of the existing plugins does this yet; the table below says what each reads today and what is missing. See also *Open questions*.

**Existing plugins.** All three read cash accounts only and emit bank lines; none emits `invest_lines`, and the Consorsbank and Scalable plugins reject depot statements on purpose.

| Plugin | Reads today | Securities activity seen as | Gap for depotbuch |
| --- | --- | --- | --- |
| [ofxstatement-consorsbank](https://github.com/ralphovi/ofxstatement-consorsbank) | Girokonto, Tagesgeld, Verrechnungskonto (PDF, CSV) | `EFFEKTEN` debit and `ZINS/DIVID.` credit on the Verrechnungskonto, cash amount only | New parser for trade and dividend confirmations (Wertpapierabrechnung) emitting investment lines |
| [ofxstatement-scalable](https://github.com/ralphovi/ofxstatement-scalable) | Cash account (PDF, English and German) | Buy and sell lines whose memo keeps units, name and ISIN, e.g. *6.25 pcs. … (IE000HY30YW6)*; trade fee as a separate line | Emit investment lines from those memos, attaching the same-day trade fee |
| [ofxstatement-revolut](https://github.com/ralphovi/ofxstatement-revolut) | Current, deposit and sub-accounts (PDF, CSV) | Not covered: trading statements are separate from bank statements | New parser for the Revolut trading statement |

Tagesgeld is covered already: Consorsbank Tagesgeld, Revolut deposit and savings interest, and Scalable cash interest arrive as `INT` lines. Securities history before go-live comes from the Parqet CSV export, so the plugin work only decides how new activities flow in.

### Market data

Securities are valued through yfinance, the one free source that covers German listings. Deposits and pension contracts need no market source: their values come from statements.

**Candidate sources for securities**

| Source | Covers | Access | Cost | Terms |
| --- | --- | --- | --- | --- |
| [yfinance](https://pypi.org/project/yfinance/) (Yahoo Finance) | Stocks, ETFs, many funds; German exchanges | Python library over Yahoo's public endpoints; Apache-2.0 | Free | Not affiliated with Yahoo; Yahoo's data is for personal use only |
| [Alpha Vantage](https://www.alphavantage.co/premium/) | US markets listed; German listings not confirmed | Documented API | Free: 25 calls a day; paid from 49.99 $ a month | Licensed |
| [Twelve Data](https://twelvedata.com/pricing) | Free: 3 exchanges, US; EU data and fund NAVs from Pro | Documented API | Free: 800 credits a day; Pro 229 $ a month | Licensed |
| [EODHD](https://eodhd.com/financial-summary/XDEQ.XETRA) | Stocks, ETFs, EU funds; ISIN search | Documented API | Free: [20 calls a day, 1 year of history](https://help.portfolio-performance.info/en/how-to/downloading-historical-prices/eodhd/); EOD plan 19.99 $ a month | Licensed for personal use |
| Manual CSV | Anything | File | Free | Own data |
| [Marketstack](https://marketstack.com/pricing) | End-of-day, global tickers; German exchanges not named | Documented API | Free: 100 calls a month, 1 year of history; Basic 9.99 $ a month | Free: non-commercial; paid: commercial allowed |
| [Interactive Brokers](https://interactivebrokers.github.io/tws-api/historical_data.html) | Exchange-listed securities incl. Xetra; no non-listed funds | TWS API via TWS or IB Gateway; IBKR account required | History needs a paid L1 subscription per exchange; previous-day close free (delayed frozen); USD 500 account equity minimum | Licensed for the account holder |

**Decision.** yfinance is the price provider for step 1: free, covers German listings, and its personal-use condition matches this tool. Interactive Brokers replaces it later as the primary source: one month of exchange subscriptions backfills the full history, then the free previous-day close keeps it current. Access comes from an invested position of about €600–700 in the existing IBKR account, which keeps equity above the USD 500 minimum. Prices go through one provider interface with a provider chosen per security, so the switch needs no change elsewhere, and manual CSV covers anything neither source has. Alpha Vantage, Twelve Data, Marketstack and EODHD are ruled out: free tiers are US-centred or too small, and every paid plan with European data costs about as much as Parqet Plus or more.

**Valuation by asset type**

| Asset type | Value on a day | Source |
| --- | --- | --- |
| Security | Units × close × FX | Price provider; ECB for FX |
| Tagesgeld | Account balance | Bank statements |
| Verrechnungskonto (broker cash) | Account balance | Bank statements; the Consorsbank and Scalable plugins read them today |
| Festgeld | Principal + interest accrued daily at the contract rate | Contract terms, then the maturity statement |
| Pension contract (step 2) | Last statement value, held flat until the next | Yearly statement; fund units × fund price where the contract reports units |

**Rules**

- Use closes adjusted for splits but not for dividends, since dividends are booked as activities.
- Carry the last close or valuation forward over weekends, holidays and between statements. Never value a held asset at zero because data is missing.
- An activity is converted at the broker's rate when the statement gives one, otherwise at the ECB rate for that day.
- Reports flag any security whose newest close is older than 5 days, and any contract whose newest valuation is older than 13 months.
- Updates are incremental: refetch from the newest stored date minus 7 days.

### Calculations

Every figure is computed in EUR, after taxes, for a time range (YTD, 1 year, since purchase, or custom) and for any slice: whole portfolio, provider, account, asset class or single asset. The terms follow Parqet's FAQ; where depotbuch deliberately differs (taxes), a Parqet-compatible mode reproduces Parqet's figures for the parallel run.

**Metrics**

| Metric (Parqet term) | Definition |
| --- | --- |
| Value (Portfoliowert) | Sum of asset values on the day, per *Valuation by asset type* |
| Invested capital (investiertes Kapital) | FIFO cost of units still held, incl. purchase fees; for deposits and contracts, the net amount paid in |
| Price gain (Kursgewinn) | Value − invested capital |
| Realized gain (realisierter Gewinn) | Sale proceeds after fees and taxes − FIFO cost of the units sold |
| Income (Dividenden) | Dividends, distributions and interest, net of withheld tax |
| Taxes | Withholding, Abgeltungsteuer, Soli and church tax on sales, dividends and interest; tax refunds negative |
| Absolute gain for a range | End value − start value − inflows + outflows + income paid out of the slice, all after taxes |
| TTWROR | Linked sub-period returns, defined below; never annualized |
| IZF | Annualized internal rate of return, defined below |

**TTWROR.** Parqet splits the range at every activity and chains the sub-period returns. Computed daily, inflows enter at the start of the day, outflows and income at the end:

```latex
1 + \mathrm{TTWROR} = \prod_{d} \frac{V_d + S_d + D_d - T_d}{V_{d-1} + B_d}
```

V is the slice's value at end of day. B is inflows: buys, deliveries in, deposits, pension contributions. S is outflows: sales, deliveries out, withdrawals, after the fees and taxes on them. D is income paid out of the slice that day, before tax, and T the tax withheld on it, so D − T is the net income that left the slice. Income credited to an account inside the slice (interest staying on Tagesgeld, a dividend landing on a Verrechnungskonto that the slice includes) is already in V and is not added as D. Taxes on sales are deducted once, in S, and are not part of T. Fees are included in B and S, so they also reduce the return.

**Parqet-compatible mode** (`--parqet`). Follows Parqet's FAQ for a portfolio with a cash account: taxes and fees on buys, sales and dividends are not counted as a loss of return, while costs booked directly to the cash account (custody or account fees) still reduce it. Used only for the parallel run.

**IZF.** The rate r that sets the net present value of all flows in the range to zero. The start value counts as an outflow on the first day and the end value as an inflow on the last day:

```latex
-V_0 + \sum_i \frac{CF_i}{(1+r)^{t_i/365}} + \frac{V_T}{(1+r)^{T/365}} = 0
```

CF is −inflows + outflows + net income paid out of the slice, all after fees and taxes. As for TTWROR, income that stays inside the slice is already in the end value and is not a flow.

**Lots.** Each buy or delivery in opens a lot. Sales close lots first-in first-out within the same account, as German tax law does. Dividends are split across the lots held on the payment date, in proportion to units. A lot reports cost, value, dividends, gain after tax, return since purchase, and the annualized return once it is at least 365 days old. Deposits and contracts have no lots; their since-purchase figure is the IZF from the first inflow.

**Taxes are attributed where they arise.** A tax on a sale or dividend belongs to that asset. Tax reported only as a yearly total (for example the Verlustverrechnung settlement at year end) belongs to the provider, so the provider and portfolio figures are correct even when no single asset can carry it.

**Cash accounts.** Each provider's Verrechnungskonto is an asset valued at its balance, so idle cash earns 0 % and lowers TTWROR, as it does in Parqet. For a single security, buys and sales stay inflows and outflows. For a provider or the portfolio, a buy or sale only moves value between the cash account and the security and is not a flow. There, the flows are transfers into or out of the cash account from untracked accounts such as the Girokonto. Dividends, interest, fees and taxes are booked where the statement shows them, usually on the cash account.

**No double counting.** A trade appears twice: as an investment activity and as its cash line on the Verrechnungskonto (for example `EFFEKTEN` at Consorsbank). Each investment activity is matched to its cash line by provider, amount and a booking date up to 3 business days later; the matched cash line is not counted again. Unmatched lines on either side are listed in the import report.

**Edge cases.** Splits restate history onto the current basis. A dividend paid after a full sale is added to the position's last held day. A range with no value at the start and no inflows yields no TTWROR (shown as —). Foreign-currency assets include the FX effect, as Parqet does.

### Views

Step 1 has seven views; six mirror a Parqet screen and the Providers view is new. Every view takes the same filters: provider, account, asset class, time range and as-of date. With no filter, a view covers the whole portfolio.

| View | Parqet counterpart | Shows |
| --- | --- | --- |
| Providers | (none; Parqet's portfolio switcher) | One row per provider and a total: value, inflows, outflows, income, taxes, absolute gain, TTWROR and IZF for the range. Selecting a row filters every other view to that provider. |
| Dashboard | Dashboard | Tiles: value, invested capital, price gain, income, realized gain, taxes, TTWROR, IZF. Chart switching between value and TTWROR over the range. Allocation by asset class and by provider. Top and bottom 3 assets by TTWROR. |
| Holdings | Position list | One row per asset, grouped by asset class: units or balance, price or valuation and its date, value, weight, invested capital, price gain (€ and %), income, realized gain, taxes, TTWROR and IZF for the range, first inflow date. Totals per class and overall. |
| Holding detail | Holding page | Header metrics as in Holdings. Price or valuation chart with buys, sales and income marked. Open and realized lots for securities; contract terms for Festgeld. The asset's activities. |
| Lots | (none) | Every open lot: provider, account, buy date, units, buy price, current price, cost, value, dividends, gain after tax, return since purchase, p.a. from 365 days, days held. |
| Income | Dividend dashboard | Dividends and interest per month, per year, accumulated, and per asset. Gross, withheld tax, net. Last 12 months total and monthly average. |
| Activities | Activities | All activities, newest first, filterable by type, provider, account and asset. Source file and import date per row. Add, edit, delete. CSV export in Parqet's import format. |

Ranges are YTD, 1 year, 3 years, since purchase and custom, as in Parqet. TTWROR is shown for the range and never annualized; IZF is always annualized.

### Interfaces

The CLI is the primary interface and covers every feature. The web front end reads the same JSON through the API. Every report command accepts `--provider`, `--account`, `--class`, `--range`, `--date`, `--parqet` and `--json`.

| Command | Purpose | View |
| --- | --- | --- |
| `depot import FILE… [-t TYPE] [-a ACCOUNT]` | Import statements, OFX or Parqet CSV | — |
| `depot account add\|edit` | Register an account: provider, asset type, and for Festgeld principal, rate and term | — |
| `depot add` / `depot edit ID` / `depot delete ID` | Manual activities | Activities |
| `depot valuation add ACCOUNT DATE VALUE` | Contract value from a statement (step 2) | — |
| `depot update [--since DATE]` | Fetch closes, splits, FX | — |
| `depot asset [ID] [--provider P] [--symbol S] [--name N]` | List assets, set price provider, symbol or name | — |
| `depot providers` | Per-provider figures and total | Providers |
| `depot dashboard` | Headline tiles and top/bottom assets | Dashboard |
| `depot holdings` | Position list | Holdings |
| `depot holding ID` | One asset in detail | Holding detail |
| `depot lots [--realized]` | Lot-level performance | Lots |
| `depot income [--by month\|year\|asset]` | Dividends and interest | Income |
| `depot activities [--type T] [--export FILE]` | List or export activities | Activities |
| `depot report -o FILE` | All views as one self-contained HTML file | all |

`depot` is a thin entry point over Django management commands, so every command runs against the same engine as the web API.

**Architecture.** A Python core with a Django backend and a TypeScript front end, deployed as a server on the homelab.

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Calculation engine | Plain Python package, `decimal.Decimal`, pydantic types; no Django imports | Lots, valuation, TTWROR, IZF, trade-to-cash matching, tax attribution |
| Adapters | Python, in-process | ofxstatement plugins, Parqet CSV, yfinance; later IBKR and FinTS |
| Backend | Django + Django Ninja | Storage via ORM and migrations; login; admin for accounts, Festgeld terms, valuations and corrections; JSON API with OpenAPI |
| CLI | Django management commands behind `depot` | Every feature, with `--json` |
| Front end | TypeScript single-page app; API client generated from the OpenAPI spec | The seven views, interactive charts, GnuCash-based design system as CSS |
| Storage | SQLite by default, PostgreSQL as an option | One database per installation |
| Deployment | Container on the homelab, behind TLS, login required | Reachable from desktop and phone |

**Rules.** The engine takes activities, prices and FX rates and returns results; Django models only store what it reads. The CLI and the front end call the same engine, so their numbers cannot differ. Quality gates: `mypy --strict` (with django-stubs), Hypothesis property tests for invariants (lots sum to holdings, no cash line counted twice, TTWROR independent of how a range is split), and the hand-computed cases from *Calculations*. Any later front-end work starts as a design proposal in the repo.

**Repository.** Own repository (`Ralphovi/depotbuch`) and its own Drive project with a context doc, separate from Autobook. The static HTML report from `depot report` remains as an offline export.

## Alternatives considered

- **Stay on Parqet Plus** (11.99 € a month as of September 2026). It is the baseline that
  *Done when* measures depotbuch against.
- **Other price sources.** Alpha Vantage, Twelve Data, Marketstack, EODHD and Interactive
  Brokers are compared under *Design → Market data*, with the reasons for choosing yfinance
  now and IBKR later.

## Graduation criteria

### Non-functional requirements

- Linux-first, Python 3.11 or later, GPL-3.0-or-later; every dependency (Django, Django Ninja, pydantic, yfinance, ofxstatement, the front-end libraries) must be GPL-compatible.
- Works offline after `depot update`. The only network calls go to the configured price and FX providers.
- Reports for 10 years of history and 100 assets finish in under 2 s.
- Imports are idempotent, and every report can be reproduced from the database and an as-of date.
- Every calculation rule in *Calculations* has a hand-computed test case, in both the default and the Parqet-compatible mode.

### Acceptance

The parallel run covers one month, uses the same activities in both tools, and runs depotbuch with `--parqet`. Deposits are left out of the comparison because the Parqet portfolio may not hold them.

| Figure | Tolerance |
| --- | --- |
| Dividends per security and year | exact to the cent |
| Realized gain per sale (FIFO) | exact to the cent |
| Invested capital per position | exact to the cent |
| Value per position on the same close | 0.01 € |
| TTWROR, YTD, total and per position | 0.1 percentage points |
| IZF, total and per position | 0.1 percentage points |

A difference beyond tolerance must be explained by one of the open questions, or it is a defect. The default, after-tax figures are accepted against hand-computed cases instead, since Parqet has no equivalent.

## Security impact

The original spec has no security section. These notes start it; architecture §14 is
still to be filled in.

- **Untrusted inputs.** Statement files (PDF, CSV, OFX) parsed in-process by ofxstatement
  plugins, Parqet CSV exports, and price, split and FX data from yfinance and ECB.
- **Sensitive data.** Account numbers, holdings and transaction history across every
  provider.
- **Exposure.** The web front end and API run on the homelab, behind TLS, with a login
  required. Outbound network calls go only to the configured price and FX providers.

## Backward compatibility

This is a new project, so nothing exists to stay compatible with. The engine's input
format, ofxstatement output, is shared with Autobook so that Autobook can take the
engine over later without changing its inputs.

## Open questions

- [ ] Plugin work order: Scalable (memo already carries units and ISIN) first, then Consorsbank trade confirmations, then Revolut trading statements? Until each is done, its new trades need manual entry or a fresh Parqet export.
- [ ] Which banks hold Tagesgeld and Festgeld, and does an ofxstatement plugin exist for each?
- [ ] What counts as "other" assets in step 1, beyond broker cash, Tagesgeld and Festgeld?
- [ ] Step 2: which pension contracts report fund units and which only a contract value? That decides how often they can be valued.
- [ ] Parallel run: does the Parqet portfolio hold every Verrechnungskonto that depotbuch tracks? Both tools must include the same cash, since idle cash dilutes TTWROR.
- [ ] Does Parqet apply FIFO per sub-depot or per portfolio? This changes realized gains when the same ISIN sits in two depots.
- [ ] IBKR (later): what does IBKR charge for German exchange Level 1 data, and how many years of daily history does one month of subscription return?

## Sources

- [finanzwissen.de: Parqet test](https://finanzwissen.de/erfahrungen/parqet), updated 23 September 2026 — feature list, tiers, prices
- [Parqet FAQ: Performancevergleich](https://faq.parqet.com/article/115-performancevergleich) — TTWROR, IZF and Rendite definitions; treatment of dividends, fees and cash
- [Parqet blog: TTWROR](https://parqet.com/en/blog/true-time-weighted-rate-of-return) — where TTWROR appears and which tier
- [Parqet blog: CSV import](https://parqet.com/en/blog/csv) and [CSV export](https://parqet.com/en/blog/export) — activity file format
- [EODHD plans](https://eodhd.com/financial-summary/XDEQ.XETRA) and [free-tier limits](https://help.portfolio-performance.info/en/how-to/downloading-historical-prices/eodhd/)
- [ofxstatement](https://github.com/kedder/ofxstatement) — plugin API and investment statement lines
