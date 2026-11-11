---
created: 12.11.2026 00:48
type: proposal
status: draft
author: Eduard Ralph
tracking-issue: https://github.com/Ralphovi/depotbuch/issues/19
supersedes:
tags:
  - proposal
  - engine
  - milestone
---
# Proposal: M1, the engine core

## Motivation

M1 is the milestone in which the numbers become right before any data is imported
(architecture §9). Its exit criterion: lots (FIFO), valuation per asset type, Festgeld
accrual, TTWROR, IZF and tax attribution pass hand-computed cases in default and
`--parqet` mode, plus Hypothesis invariants. Proposal 0001 defines the calculations; this
proposal turns them into an ordered set of pull requests, fixes the test cases that define
done for each, and settles the decisions the engine needs that 0001 leaves open.

Hand-computed cases alone check the rules as we understood them. They don't check that we
understood them right. A second source is available: the owner's complete Consorsbank
history, from the empty account in 2019 to today, with the bank's own results for every
step. A reconciliation outside the repository has already shown that it is usable:

- Replaying every trade confirmation from the empty account reproduces the units in each of
  the bank's 37 quarterly and annual holdings statements exactly, and each statement's
  positions sum to its stated total.
- FIFO cost, with fees in the cost basis, reproduces the taxable gain the bank reports for
  both sales to within 1–2 cents. No rounding mode explains the remaining cents; finding out
  what does is part of M1 (see *Open questions*).
- The history holds savings plans, lump-sum buys and sales, reinvested distributions,
  Vorabpauschale notices, a federal bond bought with accrued interest and its coupons, and
  confirmations that the bank later corrected under the same order number.

These are real figures for a real account, so none of them enters this public repository.
The design below says how they are used anyway.

## Design

### Two kinds of test case

| | Public cases | Private reconciliation |
|---|---|---|
| Where | `tests/engine/cases/` in the repository | A directory outside the repository, named by `DEPOTBUCH_PRIVATE_CORPUS` |
| Content | Invented activities, prices and expected results, each with its arithmetic written out | Activities transcribed from real statements, and the results the provider states |
| Runs in | `nox -s gate` and CI | Locally only; skipped when the variable is unset |
| Proves | Each calculation rule, as proposal 0001 defines it | That the rules, applied to a real history, agree with the provider |

A public case is shaped after a private one but invented: other amounts, dates and
placeholder ISINs. Where a private case finds a difference, the fix comes with a new public
case that reproduces it, so CI keeps guarding it.

Both kinds use one file format, a TOML case file (read with the standard library's
`tomllib`, so the harness adds no dependency) that the test harness loads into engine
types:

```toml
name = "fifo-partial-sale-with-fees"
rule = "proposal 0001, Lots"
working = """
FIFO: the sale takes all 10 units of lot 1 (1004.95) and 2 of the 5 units of lot 2
(555.00 × 2/5 = 222.00), so the units sold cost 1226.95.
Realized gain: 1435.05 − 1226.95 = 208.10.
Invested capital: the 3 units left of lot 2, 555.00 × 3/5 = 333.00.
Value: 3 × 125.00 = 375.00.
"""

[[activities]]            # engine activity types; amounts are strings, cash < 0 is paid out
date = 2024-01-02
type = "buy"
asset = "X1"
units = "10"
cash = "-1004.95"         # 1000.00 + 4.95 fees
fees = "4.95"

[[activities]]
date = 2024-03-01
type = "buy"
asset = "X1"
units = "5"
cash = "-555.00"

[[activities]]
date = 2024-06-03
type = "sell"
asset = "X1"
units = "12"
cash = "1435.05"          # 1440.00 − 4.95 fees
fees = "4.95"

[prices.X1]
2024-06-28 = "125.00"

[[expect]]
as_of = 2024-06-28
slice = { asset = "X1" }
invested_capital = "333.00"
realized_gain = "208.10"
value = "375.00"
```

The format is fixed in the first PR and is the engine's test input only. The importers
(M2, M5) produce engine types directly.

### Pull requests, in build order

Each row is one issue, one branch and one pull request. Every PR adds public cases for the
rules it implements and runs the private reconciliation for those rules before it is posted.

| # | Pull request | Rules (proposal 0001) | Done when |
|---|---|---|---|
| 1 | **Types and case harness.** `Money` (Decimal plus currency), asset, account and activity types (pydantic); the rounding policy; the TOML case loader and the private-corpus runner. | *Money and numbers* (arch. §8.6) | A case file loads into engine types and round-trips; floats are rejected; the private runner skips cleanly without the variable. |
| 2 | **Holdings and FIFO lots.** Buys, sales, deliveries in and out, splits; fees in the cost basis; nominal-quoted bonds; invested capital and realized gain. | *Lots*, *Edge cases* (splits) | Public cases for partial sales across lots, a split, a delivery with stated cost basis; property: lots sum to holdings. Private: units match every holdings statement, and both sale gains match the bank within the tolerance set under *Open questions*. |
| 3 | **Valuation per asset type.** Security units × close × FX, a bond as nominal × price in percent, cash balances, Festgeld accrual, carry-forward over gaps. | *Valuation by asset type* (arch. §8.2) | Public cases for each asset type and an FX case; private: the value of each position in each holdings statement, from the statement's own price, to the cent. |
| 4 | **Income and taxes.** Dividends split across lots by the day before the ex-date; withheld tax; tax attribution to the asset or the provider; Vorabpauschale. | *Lots* (dividends), *Taxes are attributed where they arise* | Public cases for a dividend after a partial sale, one without an ex-date (marked approximate), a year-end tax total on the provider; private: net income per distribution equals the notice. |
| 5 | **Flows: the slice rule.** Classifying every booking into B, S, R or no flow for a given slice. | *Flows: the slice rule* | One public case per row of the classification table in 0001, for each slice the row names. |
| 6 | **TTWROR and absolute gain.** | *TTWROR*, *Absolute gain* | The hand-computed case in 0001 and the dividend and fee examples there; property: TTWROR over a range equals the product over any split of it. |
| 7 | **IZF.** Root finding on the daily flows, with the start and end value as flows. | *IZF* | Public cases with a known closed-form rate; property: NPV at the found rate is zero within 1e-9 of the flows' magnitude; no-solution and multiple-root cases are reported, not guessed. |
| 8 | **Parqet-compatible mode.** | *Parqet-compatible mode* | Every case from PRs 4–7 that involves fees or taxes runs in both modes, with the expected `--parqet` result written out. |

PRs 5 to 7 depend on 2 to 4 only through the engine types, so 7 can start as soon as 1 has
landed.

### Decisions this proposal makes

These fill gaps in proposal 0001. Each is small enough to live here; anything that turns
out foundational becomes an ADR instead.

- **Rounding.** Intermediate results keep full `Decimal` precision. Amounts round to the
  cent with `ROUND_HALF_UP` only where a provider rounds (a booked cash amount, a reported
  tax) and for display. Unit counts keep the precision the statement gives. This resolves
  the open point in architecture §8.6, subject to the cent question below.
- **Vorabpauschale is an activity, not income.** The engine doesn't compute it, since that
  needs the Basiszins and the fund's year-start and year-end prices. It takes the amount from
  the provider's notice. Any tax withheld on it is a tax of that asset (R, negative, for the
  asset alone). The amount itself is no flow and no income, and is stored so that a later
  sale's taxable gain can be reduced by it.
- **A correction replaces the activity with the same identity.** When a provider reissues a
  confirmation under the same order number with changed figures, the newer one replaces the
  older one (account + `FITID`). The engine only ever sees the current activity; the
  replacement itself is import behaviour, recorded here so that M2 and M5 build it, and the
  real case becomes a public fixture then.
- **Bonds.** Units are the nominal amount and the price is in percent, so value is nominal
  × price / 100. Accrued interest paid on purchase is part of the buy's cash amount and so
  of invested capital; the coupon is income on its payment date. Whether depotbuch should
  instead show the paid accrued interest as negative income, as German tax treats it, is an
  open question.

### Out of scope for M1

Trade-to-cash matching (M5), the importers and their correction handling (M2, M5), market
data fetching (M3), storage (M4). The engine's tax figures are those the provider withholds
or reports; computing German tax liability (allowance, loss pots, partial exemption) is not
an engine feature. The private reconciliation reads those figures from the statements to
check FIFO, not to reproduce the tax computation.

## Alternatives considered

- **Hand-computed cases only.** Cheaper, but checks the rules only against our own reading
  of them. The 1–2 cent gap on real sales would not have shown up.
- **Commit anonymized real statements.** Rewriting amounts in a real statement keeps its
  shape but breaks its arithmetic, and a missed field leaks data into a public repository
  that cannot take it back. Invented cases shaped after the real ones give the same
  coverage without that risk.
- **One large engine PR.** Each rule is reviewed against its own cases more reliably in a
  PR of its own, and a mistake in FIFO doesn't block reviewing IZF.

## Graduation criteria

M1 is done when:

1. Every calculation rule in proposal 0001 has at least one public hand-computed case, in
   default and `--parqet` mode where the modes differ (architecture §13).
2. The Hypothesis properties hold: lots sum to holdings, and TTWROR is independent of how a
   range is split.
3. The private reconciliation of the Consorsbank history passes: units match every holdings
   statement, position values match each statement's prices to the cent, net income matches
   every distribution notice, and both realized sales match the bank within the tolerance
   decided under *Open questions*.
4. `nox -s gate` passes on Python 3.11 to 3.14, and the engine still imports without Django.

## Security impact

No new untrusted input enters the product: the engine reads typed values from the test
harness. The private corpus is new sensitive data on the developer's machine, holding
account numbers, names and the full transaction history:

- It lives outside the repository and is named only by an environment variable, so it
  cannot be committed by accident.
- CI never sets the variable; the runner skips without it.
- Test failures from the private runner report case names and differences, never the
  activities themselves, so a pasted test log doesn't leak a statement.

The PR that adds the runner updates the threat model (architecture §14 and
`.oss-scanner/threat_model.md`) with this asset.

## Backward compatibility

Nothing exists yet to stay compatible with. The case file format is internal to the tests
and may change with the engine types.

## Open questions

- [ ] **The remaining cents.** FIFO cost reproduces the bank's taxable sale gain to within
  1–2 cents, in both directions, and no rounding mode (half-up, half-even, down; per lot or
  per sale) closes the gap. Candidates: the bank's cost per lot is stored with a different
  precision, or reinvested distributions enter the cost basis differently. Until this is
  explained, what tolerance does the private reconciliation allow on realized gains, and
  does the explanation change how depotbuch computes invested capital?
- [ ] **Paid accrued interest on bonds:** part of the purchase cost (as above), or negative
  income in the year it is paid, as German tax treats it?
- [ ] **Which Consorsbank date is the ex-date?** Its distribution notices give a
  *Schlusstag* but no separate ex-date. If the Schlusstag is the last day that carries the
  entitlement, the lots held at its end are those 0001 asks for, which also answers part of
  0001's open question on ex-dates.
- [ ] **Further private corpora.** Scalable (statements and tax certificate from 2025 on)
  and the Revolut Tagesgeld (interest with foreign withholding tax, and closing the account)
  are next; do they belong in M1 or in the milestone that imports them?
