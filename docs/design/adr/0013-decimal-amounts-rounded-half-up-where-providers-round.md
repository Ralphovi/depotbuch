---
created: 12.11.2026 02:07
type: adr
status: Proposed
tags:
  - adr
  - engine
  - correctness
---
# 0013. Decimal amounts, rounded half up only where a provider rounds

## Context

Every figure depotbuch shows must be right to the cent, and the parallel run compares
dividends, realized gains and invested capital with Parqet to the cent (proposal 0001,
*Acceptance*). Providers state amounts in cents but compute them from unit counts, prices
and FX rates with more digits: a savings-plan buy books 116.00 EUR for 2.57715 units at
45.0109 EUR. Architecture §8.6 already requires `decimal.Decimal` from parsing to output and
left open the rounding mode and the precision of stored prices and FX rates. Proposal 0002
asks the first engine PR to settle it.

Binary floats cannot represent most cent amounts exactly, and their errors surface as
cent differences far from where they arise. Rounding intermediate results to the cent has
the same effect: a partial sale's share of a lot's cost, rounded and then summed over many
lots, drifts from the provider's figure.

## Decision

We will hold every amount, unit count, price and FX rate as `decimal.Decimal`, and refuse
binary floats at every boundary: a float passed to an engine type is rejected, not
converted.

- Intermediate results keep full precision. The engine MUST NOT round a value it passes on
  to another calculation.
- An amount is rounded to the cent only where a provider rounds it (a booked cash amount, a
  withheld or reported tax) and for display and comparison. Rounding is half up
  (`ROUND_HALF_UP`), as German banks round.
- Unit counts, prices and FX rates are stored with the digits the source gives and are
  never rounded by depotbuch.
- The engine's types carry each amount's currency until it is converted to EUR.

We reject binary floats, rounding at every step, and banker's rounding (half even), which
no German bank in the history examined uses.

## Consequences

- A figure computed from stored activities is reproducible, and a difference to a
  provider's figure points to a rule, not to accumulated rounding.
- Every boundary has to convert: parsers, the case harness and later the Django models use
  `Decimal` fields, and test data writes amounts as strings.
- The private reconciliation of the Consorsbank history still differs from the bank's
  taxable sale gains by 1–2 cents, which no rounding mode explains (proposal 0002, *Open
  questions*). If the explanation turns out to be a provider's own rounding of an
  intermediate value, such as a lot's cost, that rounding is modelled where the provider
  applies it, and this record is superseded if the rule above has to change.
