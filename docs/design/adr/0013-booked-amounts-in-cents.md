---
created: 12.11.2026 02:07
type: adr
status: Proposed
tags:
  - adr
  - engine
  - correctness
---
# 0013. Booked amounts in cents, analytical figures at full precision

## Context

Every figure depotbuch shows must be right to the cent, and the parallel run compares
dividends, realized gains and invested capital with Parqet to the cent (proposal 0001,
*Acceptance*). Architecture §8.6 requires `decimal.Decimal` from parsing to output and left
open where amounts are rounded.

The engine handles two different kinds of number. Some are bookings: the cash of a trade,
its fees and taxes, a lot's cost, the part of that cost a partial sale takes, the part of a
sale's proceeds that falls on each lot, an amount converted from another currency. A bank
books each of these in cents when it comes into existence, rounding half up, and the parts
of a split amount add up to the amount. Others are analysis: a daily return factor, TTWROR,
IZF. They are ratios, never booked. A position's value sits between: no bank books it, but
a holdings statement shows it to the cent and adds its total from those cents.

Carrying bookings at the full precision of Python's decimal context (28 significant digits)
is not an accounting rule. It leaves fractions of a cent in costs and gains that no ledger
holds, lets the parts of a split amount differ from the whole in the last digit, and makes
a figure depend on the arithmetic context rather than on a rule a bank would recognize.

## Decision

We will hold every amount, unit count, price and FX rate as `decimal.Decimal` and reject
binary floats at every boundary. Beyond that, two rules apply.

**Booked amounts are in cents.**

- An activity's booked fields (cash, fees, taxes, a delivery's cost basis, a Vorabpauschale
  amount) MUST be whole cents below 10^15, units MUST be below 10^15 with at most 12
  decimals, and an FX rate or split ratio MUST lie between 0.000001 and 1,000,000 (a ratio
  with at most 12 decimals); anything else is rejected, and a split whose result leaves the
  unit bounds fails. Within those bounds sums fit Python's default 28-digit decimal context.
- A share or a conversion is computed as an exact fraction and rounded to the cent once;
  a quotient first rounded to the context's 28 digits could land on the wrong cent.
- An amount the engine books is rounded to the cent, half up, when it comes into existence:
  a conversion to EUR, at the broker's rate or else the ECB rate (`FxRates.book_eur`).
- A booked amount is split in cents so that the parts add up to it exactly. A partial sale
  takes `book(lot cost × units sold / lot units)` and leaves the lot exactly the rest; a
  sale's proceeds and taxes are split across the lots it closes pro rata to units, each part
  booked and the last taking what is left (`money.share`, `money.allocate`).
- Sums of booked amounts are therefore exact, and checks on them need no tolerance.

**Where a statement shows a figure, the statement wins.** If depotbuch and a provider's
statement could differ by a cent, depotbuch rounds where the statement rounds. A
position's value is computed exactly and rounded to the cent once, half up, and the value
of a slice is the sum of its positions' cents, as a holdings statement adds up its total.

**Analytical figures keep full precision.** Return factors, TTWROR and IZF are computed
without intermediate rounding and rounded only for display and comparison. Unit counts,
prices and FX rates keep the digits their source gives and are never rounded by depotbuch.

We reject carrying bookings at full precision, rounding analytical figures at each step,
and banker's rounding (half even), which no German bank in the history examined uses.

## Consequences

- Invested capital, realized gains and every other sum of bookings are whole cents and add
  up exactly, the way a bank statement does.
- Each boundary converts: parsers, the case harness and later the Django models use
  `Decimal` fields, and test data writes amounts as strings.
- Where depotbuch books an amount a provider also books (a lot's cost share, a converted
  amount), the provider's own rule decides the cent. Half up per booking is the rule
  observed so far. Where a provider books at another point, that point is modelled: the
  Consorsbank partial exemption is rounded per lot from a price per unit rounded to four
  decimals, which the private reconciliation now matches to the cent. This record is
  superseded only if the rule itself has to change.
- A portfolio total matches the statement's to the cent. It can differ by a cent from the
  same positions summed at full precision; the statement's total is the one shown.
