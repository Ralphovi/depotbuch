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
  both sales (proceeds after fees, less FIFO cost, less the 30 % partial exemption for
  equity funds) to within 1–2 cents. No rounding mode explains the remaining cents; finding out
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
units = "-12"             # signed as in proposal 0001's activity mapping
cash = "1435.05"          # 1440.00 − 4.95 fees
fees = "4.95"

[assets.X1]
currency = "EUR"          # a USD asset adds [fx.USD]: USD per EUR per day, as the ECB quotes it

[prices.X1]               # closes in the asset's currency
2024-06-28 = "125.00"

[[expect]]
as_of = 2024-06-28
slice = { asset = "X1" }
invested_capital = "333.00"
realized_gain = "208.10"
value = "375.00"
```

PR 1 defines the format, including currencies (`[assets]`, with EUR as the default) and FX
rates (`[fx.<currency>]`, per day). Rates are stored as the ECB quotes them, units of the
foreign currency per EUR, so a value in EUR is the amount in that currency divided by the
rate: a close of 100 USD at 1.20 USD per EUR is 83.33 EUR. An activity carries its own
`currency` (the settlement currency, EUR by default) and, when the broker states one, its
`fx_rate` in the same direction; without it the ECB rate for the activity's date applies. Later PRs only add to it. It is the engine's test input
only; the importers (M2, M5) produce engine types directly.

### Pull requests, in build order

Each row is one issue, one branch and one pull request. Every PR adds public cases for the
rules it implements and runs the private reconciliation for those rules: before it is posted when the owner or
the owner's agent wrote it, and for a contributor's PR after the owner has reviewed its code
and before it is merged.

| # | Pull request | Rules (proposal 0001) | Done when |
|---|---|---|---|
| 1 | **Types and case harness.** `Money` (Decimal plus currency), asset, account and activity types (pydantic); the rounding policy; the TOML case loader and the private-corpus runner. | *Money and numbers* (arch. §8.6) | A case file loads into engine types and round-trips, including a foreign-currency asset with FX rates; floats are rejected; the private runner skips cleanly without the variable. The runner refuses a corpus directory that resolves to a path inside any worktree of the repository (`git worktree list`), before reading or writing anything. It names cases by their file name, which the owner keeps synthetic (`c01.toml`), and reports parse and validation errors by file, field and error kind, never with the input's text. Tests with captured stdout and stderr feed it a failing case, a malformed TOML file, a value that fails validation a corpus path inside the checkout and one inside a sibling worktree, and assert that no value from the case file, and no key the case defines (asset and account names, dates), appears in the output; the fixed field names of the format may. |
| 2 | **Holdings and FIFO lots.** Buys, sales, deliveries in and out, splits; fees in the cost basis; nominal-quoted bonds; invested capital and realized gain. | *Lots*, *Edge cases* (splits) | Public cases for partial sales across lots, a split, a delivery with stated cost basis, and the same asset in two accounts where a sale from one must not consume the older lot in the other; a USD buy and sale, once with the broker's rate on each activity and once without, so that cost and realized gain use the broker's rate when given and the ECB rate otherwise; property: lots sum to holdings. Private: units match every holdings statement, and for both sales the pre-tax FIFO gain, less the partial exemption and less any Vorabpauschale already assessed on the units sold (taken from the notices), matches the bank's taxable gain within the tolerance set under *Open questions*. That comparison lives in the private harness; the engine's realized gain stays the after-tax figure 0001 defines. |
| 3 | **Valuation per asset type.** Security units × close converted to EUR (divided by the ECB rate), a bond as nominal × price in percent, cash balances, Festgeld accrual, carry-forward over gaps. | *Valuation by asset type* (arch. §8.2) | Public cases for each asset type; an FX case whose expected value only holds if the rate is divided, not multiplied; Festgeld cases for each supported day-count convention (actual/365, actual/360 and 30E/360, the European 30/360 used by German banks, held in the account's Festgeld terms along with whether interest accrues on the start day and the maturity day), including a deposit across 29 February, one that starts or ends on the 31st of a month, and the value on the maturity day itself; a carry-forward case valued on a day after the last close and the last FX rate, which must use those and never zero. Private: the value of each position in each holdings statement, from the statement's own price, to the cent. |
| 4 | **Income and taxes.** Dividends split across lots by the day before the ex-date; withheld tax; tax attribution to the asset or the provider; Vorabpauschale. | *Lots* (dividends), *Taxes are attributed where they arise* | Public cases for a dividend after a partial sale, one paid after a full sale (to the lots held before the ex-date, and without an ex-date to the position's last held day), one without an ex-date while units are held (marked approximate), a year-end tax total on the provider; private: net income per distribution equals the notice. |
| 5 | **Trade-to-cash matching.** Pairing each investment activity with its cash line on the Verrechnungskonto by provider, amount and a booking date up to 3 business days later; listing what stays unmatched. | *No double counting* | Public cases for a match on the third business day, a near-miss on the fourth, two trades of equal amount, and an unmatched line on each side; property: no cash line is counted twice. |
| 6 | **Flows: the slice rule.** Classifying every booking into B, S, R or no flow for a given slice. | *Flows: the slice rule* | One public case per row of the classification table in 0001, for each slice the row names. |
| 7 | **TTWROR and absolute gain.** | *TTWROR*, *Absolute gain* | The hand-computed case in 0001 and the dividend and fee examples there; property: for any split of a range into consecutive subranges, 1 + TTWROR of the range equals the product of 1 + TTWROR of the subranges. |
| 8 | **IZF.** Root finding on the daily flows, with the start and end value as flows. | *IZF* | Public cases with a known closed-form rate; property: NPV at the found rate is zero within 1e-9 of the flows' magnitude; no-solution and multiple-root cases are reported, not guessed. |
| 9 | **Parqet-compatible mode.** | *Parqet-compatible mode* | Every public case runs in both modes. A case states a separate `--parqet` expectation only where the result differs, and otherwise must give the same result in both. The differing cases include a buy and a sale with fees and a sale with withheld tax, for a single security and for its provider. |

The root finder in PR 8 depends on the other PRs only through the engine types, so it can
start as soon as PR 1 has landed.

### Decisions M1 needs

Proposal 0001 leaves these open. This proposal states the intended direction; the PR that
implements each one records it as a Proposed ADR (rounding in PR 1, bonds in PR 2,
Vorabpauschale in PR 4), so the decision itself goes through the ADR process.

- **Rounding.** Intermediate results keep full `Decimal` precision. Amounts round to the
  cent with `ROUND_HALF_UP` only where a provider rounds (a booked cash amount, a reported
  tax) and for display. Unit counts keep the precision the statement gives. This resolves
  the open point in architecture §8.6, subject to the cent question below.
- **Vorabpauschale is an activity, not income.** The engine doesn't compute it, since that
  needs the Basiszins and the fund's year-start and year-end prices. It takes the amount from
  the provider's notice. Any tax withheld on it is a tax of that asset (R, negative, for the
  asset alone). The amount itself is no flow and no income, and is stored so that a later
  sale's taxable gain can be reduced by it.
- **Bonds.** Units are the nominal amount and the price is in percent, so value is nominal
  × price / 100. Accrued interest paid on purchase is part of the buy's cash amount and so
  of invested capital; the coupon is income on its payment date. Whether depotbuch should
  instead show the paid accrued interest as negative income, as German tax treats it, is an
  open question.

### Out of scope for M1

The importers and their handling of corrections (M2, M5), market data fetching (M3),
storage (M4). Matching is built here as an engine function; M5 feeds it real cash lines. The engine's tax figures are those the provider withholds
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

1. Every calculation rule in proposal 0001 has at least one public hand-computed case, and
   every public case passes in both default and `--parqet` mode, with a separate expected
   result where the modes differ (architecture §13).
2. The Hypothesis properties hold: lots sum to holdings, no cash line is counted twice, and
   TTWROR is independent of how a range is split.
3. The private reconciliation of the Consorsbank history passes: units match every holdings
   statement, position values match each statement's prices to the cent, net income matches
   every distribution notice, and for both sales the pre-tax FIFO gain after the partial
   exemption and any Vorabpauschale already assessed on the units sold matches the bank's
   taxable gain within the tolerance decided under *Open questions*.
4. `nox -s gate` passes on Python 3.11 to 3.14, and the engine still imports without Django.

## Security impact

No new untrusted input enters the product: the engine reads typed values from the test
harness. The private corpus is new sensitive data on the developer's machine, holding
account numbers, names and the full transaction history:

- It lives outside the repository and is named only by an environment variable. The runner
  refuses a corpus path inside any worktree of the repository, so neither the corpus nor its
  report can be committed by accident.
- The corpus is exposed only to code the owner trusts: branches the owner or the owner's
  agent wrote, or that have been reviewed. It is never run against code the owner hasn't
  reviewed, since the code under test sees the real values and could print or send them. Where the platform allows, the run has no network access
  (`unshare -rn` on Linux).
- CI never sets the variable; the runner skips without it.
- The private runner prints only synthetic case file names, field names and pass or fail;
  parse and validation errors name the file, field and error kind, never the input's text. Expected and
  actual values, and the differences between them, go to a report file inside the corpus
  directory, so a pasted test log or CI output carries no amounts.

This PR adds the private corpus to the threat model (architecture §14 and
`.oss-scanner/threat_model.md`); the PR that adds the runner adds its test.

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
- [ ] **Corrections and their order.** The Consorsbank history holds confirmations reissued
  under the same order number with a changed cash amount, while architecture §8.7 skips an
  activity whose account + `FITID` is already stored. Should a reissue replace the stored
  activity, and how is "newer" decided when an original arrives after its correction: the
  provider's document date, an explicit correction marker, or a conflict the owner resolves?
  This is import behaviour, settled in M2 together with an update to §8.7; the engine only
  ever sees the current activity.
- [ ] **Further private corpora.** Scalable (statements and tax certificate from 2025 on)
  and the Revolut Tagesgeld (interest with foreign withholding tax, and closing the account)
  are next; do they belong in M1 or in the milestone that imports them?
