---
created: 10.11.2026 19:03
type: architecture
status: living
tags:
  - architecture
---
# 8. Cross-cutting concepts

> Living document. The core ideas the rest of the design is built on. Terms are also in the glossary (section 12). Open questions are marked **[OPEN]** inline.

## 8.1 Activities are the only stored fact

An activity (buy, sell, dividend, interest, transfer, fee, split, deposit, withdrawal, and in
step 2 contribution and allowance) is the only fact depotbuch stores about a position.
Holdings, lots, values and every report are recomputed from activities plus market data.
Re-imports, corrections and method changes (FIFO to average, say) therefore need no data
migration (ADR-0006, Proposed).

One portfolio holds all providers; a provider holds accounts (a depot, a Verrechnungskonto, a
Tagesgeld account, each Festgeld deposit); an account holds activities, and each activity
refers to one asset. A position is an asset across accounts. In step 2, a pension contract
is one more account whose asset is the contract, valued from its statements.

The spec's domain-model diagram (6 stored entities, 3 derived) was lost when the spec was
exported to Markdown. The diagram below is **reconstructed from the spec text**; the exact
entity split is to be confirmed when the models are written.

```mermaid
classDiagram
  direction LR
  class Portfolio
  class Provider {
    name
  }
  class Account {
    BROKERID:ACCTID
    asset type
    Festgeld terms
  }
  class Asset {
    ISIN or own key
    class
    price provider, symbol
  }
  class Activity {
    account + FITID
    type, date
    units, cash, fees, taxes
    source file, import date
  }
  class MarketData {
    close per asset and day
    split
    FX rate per day
    valuation (contracts)
  }
  class Position {
    <<derived>>
    asset across accounts
  }
  class Lot {
    <<derived>>
    FIFO, per account
  }
  class Holding {
    <<derived>>
    units, value, figures per range
  }

  Portfolio "1" --> "*" Provider
  Provider "1" --> "*" Account
  Account "1" --> "*" Activity
  Activity "*" --> "1" Asset
  Asset "1" --> "*" MarketData
  Position ..> Activity : derived from
  Lot ..> Activity : opened by buy or delivery in
  Holding ..> MarketData : valued with
```

## 8.2 Valuation

Every figure is computed in EUR, for a time range and for any slice: whole portfolio,
provider, account, asset class or single asset.

| Asset type | Value on a day |
|------------|----------------|
| Security | Units × close, divided by the ECB rate for a foreign currency (quoted as units of that currency per EUR). Closes are adjusted for splits but not for dividends, which are booked as activities. |
| Bond | Nominal × price in percent / 100, converted the same way (ADR-0014). |
| Tagesgeld, Verrechnungskonto | Account balance: the sum of the cash its bookings moved. A booking without an asset (deposit, withdrawal, interest, fee, tax) belongs to its account's own balance; a cash asset may also be named. |
| Festgeld | Balance plus simple interest accrued daily under the account's terms (principal, rate, start, maturity, day count act/365, act/360 or 30E/360, and whether the start and maturity days earn) and not yet credited; accrual stops at maturity, and the payout closes it (ADR-0015). An account with deposit terms is a Festgeld. |
| Pension contract (step 2) | Last statement value held flat until the next; fund units × fund price where the contract reports units. |

The last close or valuation is carried forward over gaps; a held asset is never valued at
zero for lack of data: with no close or rate on or before the day, valuation fails
(`MissingPrice`, `MissingRate`) rather than counting it as zero. Each position's value is
computed exactly and rounded to the cent once; a slice's value is the sum of those cents,
as a holdings statement adds up its total (ADR-0013). `engine/valuation.py` computes it. An activity is converted at the broker's rate when the statement gives
one, otherwise at the ECB rate for that day. Foreign-currency assets include the FX effect.

## 8.3 Lots and FIFO

Each buy or delivery in opens a lot. Sales close lots first-in first-out within the same
account, as German tax law does (`depotbuch.engine.lots`). A lot's cost is the cash paid for
it in EUR, so purchase fees, any tax and any accrued interest paid with it are part of
invested capital; a sale's realized gain is its cash received after fees and taxes less the
cost of the units it closes. A sale larger than the account's holding is rejected. A
delivery in keeps its stated cost basis on the lot, while performance counts it at market
value on the transfer date (§8.4); a delivery out closes lots without realizing a gain.
Bonds are lots like any other, with the nominal amount as units (ADR-0014, Proposed). Dividends are split
across the lots held at the end of the day before the ex-date, in proportion to units; the
payment date stays the date of the income flow. Without an ex-date, the lots held on the
payment date are used and the split is marked as approximate. **[OPEN]** Which sources give
the ex-date: OFX `INCOME` and the Parqet CSV do not. Splits restate history onto the current
basis: a split multiplies the units of the account's open lots by its ratio, keeps their
cost, and takes effect at the start of its day. A dividend paid after a full sale belongs to the lots held before the ex-date;
without an ex-date it is added to the position's last held day. Average and LIFO are later
options; because lots are derived, adding them needs no migration.

**[OPEN]** Does Parqet apply FIFO per sub-depot or per portfolio? This changes realized gains
when the same ISIN sits in two depots, and so the parallel run.

## 8.4 Performance and taxes

- **The slice rule decides what is a flow.** A slice is a set of holdings (a security in an
  account, or an account's cash balance). Every booking, with its matched cash line, has an
  asset side and a cash side. If both sides are inside the slice, the booking is no flow:
  what it earns or costs is already in the slice's value. If one side is inside, it crosses
  the slice's edge and is an inflow B (start of day), an outflow S (end of day), or return R
  settled through an account outside the slice (end of day; income positive, expenses and
  taxes negative). Capital crosses at what it is worth then: a trade at its cash amount
  including its fees and taxes, a delivery at market value on the transfer date (its cost
  basis stays with the lot). So a buy is a flow for the security alone but not for its
  provider, a dividend is return for the security, no flow for the provider, and an inflow
  for the Verrechnungskonto alone.
- **TTWROR** chains daily factors (V<sub>d</sub> + S<sub>d</sub> + R<sub>d</sub>) /
  (V<sub>d−1</sub> + B<sub>d</sub>). A day on which the slice holds nothing is a neutral
  factor of 1. Shown for the range, never annualized; a range with no start value and no
  inflows has no TTWROR (shown as —).
- **Absolute gain** is V<sub>end</sub> − V<sub>start</sub> − ΣB + ΣS + ΣR.
- **IZF** is the annualized internal rate of return over the daily cash flows −B + S + R,
  with the start value as an outflow on the first day and the end value as an inflow on the
  last.
- **Taxes are deducted by default** (withholding, Abgeltungsteuer, Soli, church tax; refunds
  negative). A tax on a sale or dividend belongs to that asset; a tax reported only as a
  yearly total belongs to the provider, so provider and portfolio figures stay right.
- **Parqet-compatible mode** (`--parqet`) follows Parqet's FAQ: taxes and fees on buys, sales
  and dividends do not reduce the return, while costs booked directly to the cash account
  still do. It exists only for the parallel run (ADR-0012, Proposed).

The formulas, the full classification table and the hand-computed cases are in proposal
0001, *Calculations*.

## 8.5 Cash accounts and no double counting

Each provider's Verrechnungskonto is a holding valued at its balance, so idle cash earns 0 %
and lowers TTWROR, as in Parqet. Under the slice rule (§8.4), a provider's or the
portfolio's flows are the transfers to and from untracked accounts such as the Girokonto.
Whether a bank line is such a transfer is decided by the account configuration, not guessed.

A trade appears twice, as an investment activity and as its cash line (for example `EFFEKTEN`
at Consorsbank). Each investment activity is matched to its cash line by provider, amount and
a booking date up to 3 business days later; the matched line is not counted again, and
unmatched lines on either side are reported.

**[OPEN]** Parallel run: does the Parqet portfolio hold every Verrechnungskonto that depotbuch
tracks? Both tools must include the same cash, since idle cash dilutes TTWROR.

## 8.6 Money and numbers

Amounts, unit counts, prices and FX rates are `decimal.Decimal` from parsing to output; a
binary float is rejected at every boundary, not converted (`depotbuch.engine.money`). Each
amount carries its currency until it is converted to EUR. Two kinds of number follow
different rules (ADR-0013, Proposed):

- **Booked amounts** (cash, fees, taxes, a lot's cost, the share of cost or proceeds a sale
  assigns to a lot, an amount converted to EUR) are in cents. An activity's booked fields
  must be whole cents below 10^15 (units below 10^15 with at most 12 decimals, FX rates
  between 10^-6 and 10^6, so sums fit the default decimal context); a share or conversion
  is computed exactly and rounded once; an amount the engine books is rounded half up when it comes into
  existence; a booked amount is split in cents whose parts add up to it exactly.
- **Values** are rounded where a holdings statement rounds them: each position to the cent
  from its exact value, and a total as the sum of those cents. Where depotbuch and a
  statement could differ by a cent, the statement wins.
- **Analytical figures** (return factors, TTWROR, IZF) keep full precision and are
  rounded only for display and comparison. Unit counts, prices and FX rates keep the digits
  the source gives.

## 8.7 Imports: identity, reporting, nothing silent

- An activity's identity is account plus `FITID`; Parqet rows use a hash of the row plus its occurrence number among identical rows in the file.
- The security key is the ISIN; tickers and WKNs are mapped once and remembered.
- The account is `BROKERID:ACCTID` from the statement, overridable per import.
- Each import reports added, skipped and rejected rows, and unmatched cash lines. Nothing is
  dropped silently.
- A sale larger than the holding is rejected with the date and the missing units.

## 8.8 Build and CI

`nox -s gate` is the single gate, run locally and as the required `gate` check in CI: ruff
format and lint (including the banned-API rule that keeps Django out of the engine and
adapters), mypy `--strict` with django-stubs, pytest with Hypothesis, typos and the docs
checks. CI also runs the test suite on Python 3.11 to 3.14. Every action is pinned to a
commit hash.

## 8.9 Security

The threat model is §14, summarized for reviewers in
[`.oss-scanner/threat_model.md`](../../../.oss-scanner/threat_model.md). A change that adds an
untrusted input (a new statement format, plugin, price source or API endpoint) or moves a
trust boundary (login, deployment, network exposure) updates both in the same PR.
