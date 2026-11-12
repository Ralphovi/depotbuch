---
created: 12.11.2026 13:30
type: adr
status: Proposed
tags:
  - adr
  - engine
  - valuation
---
# 0015. Festgeld: simple interest accrued daily under the account's terms

## Context

Proposal 0001 values a Festgeld as its principal plus interest accrued daily at the contract
rate, until the maturity statement, with principal, rate, start and maturity entered once
with the account. Banks don't agree on how the days are counted: some use actual days over
365, some over 360, and many German banks the European 30/360 (30E/360), where every month
has 30 days and a 31st counts as the 30th. They also differ on whether the start day and
the maturity day earn interest. Between maturity and the bank's statement, the money has
stopped earning but hasn't been paid out yet. And a bank may credit interest before
maturity, which then sits in the balance as well as in the accrual.

## Decision

We will value a Festgeld from its activities and its account's terms:

- The terms are principal, nominal rate in percent per year, start, maturity, the day
  count (act/365, act/360 or 30E/360) and whether the start day and the maturity day earn
  interest. They are entered once with the account; act/365 with the start day earning and
  the maturity day not is the default.
- Interest is simple: principal × rate × interest days / days in the year (365 for act/365,
  even in a leap year; 360 otherwise). The earning days run from the start to the maturity,
  without the start or the maturity day unless its flag says so. By the end of a day, each
  earning day up to it has earned what the convention counts from it to the next day, so
  the count never goes down; after maturity it stops.
- The value is the account's balance, from its bookings, plus the interest accrued and not
  yet credited (gross: a credit's net amount plus the tax withheld from it). An account with
  deposit terms holds one Festgeld: every booking in it belongs to that balance, whatever
  asset it names, and a booking that moves units there is an error. A credit rounded to
  the cent may exceed the accrual; then nothing is left to accrue, and the value never
  falls below the balance. Once a withdrawal on or after maturity pays the deposit out, the value is
  the balance alone: the statement is what happened.
- The accrual is an analytical figure at full precision (ADR-0013); the interest the bank
  credits is a booked amount, in cents.

We reject compounding within a term and day counts beyond these three until a real deposit
needs them.

## Consequences

- A Festgeld with an unusual convention needs a new `DayCount`, not a new code path.
- Under 30E/360 a 31st earns nothing and the last day of February earns up to 3 days, so the
  daily value steps there, as the convention does.
- A multi-year Festgeld that compounds yearly is valued a little low until the bank
  credits the year's interest, after which the balance carries it. If that matters, a later
  ADR adds compounding to the terms.
- A Festgeld account without terms can't be valued and fails rather than showing its
  principal alone.
