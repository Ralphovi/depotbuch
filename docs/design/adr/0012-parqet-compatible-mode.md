---
created: 11.11.2026 03:11
type: adr
status: Proposed
tags:
  - adr
  - calculations
  - acceptance
---
# 0012. A Parqet-compatible mode, for the parallel run only

## Context

depotbuch reports every figure after taxes by default (proposal 0001, *Calculations*).
Parqet does not: following its FAQ, taxes and fees on buys, sales and dividends are not
counted as a loss of return, while costs booked directly to the cash account still are.
Step 1 is done when one parallel-run month shows depotbuch agreeing with Parqet within the
acceptance tolerances (proposal 0001, *Acceptance*): exact to the cent for dividends,
realized gains and invested capital, 0.1 percentage points for TTWROR and IZF. With
different tax and fee treatment, the two could never agree, and a real defect could hide
behind the expected difference.

## Decision

We will offer a Parqet-compatible mode, `--parqet` on every report command, that follows
Parqet's FAQ on taxes and fees. It changes only that treatment; activities, valuation and
the slice rule stay the same. It exists only for the parallel run. The default figures
stay after taxes and are accepted against hand-computed cases instead, since Parqet has no
equivalent.

Every calculation rule has a hand-computed test case in both modes (proposal 0001,
*Non-functional requirements*).

## Consequences

- The parallel run can compare like with like, so a difference beyond tolerance is a defect
  or one of the listed open questions, not the tax treatment.
- Each calculation rule is tested twice, and the mode is a second code path to keep right.
- After the parallel run, the mode has no user-facing purpose. Whether to keep it as a
  diagnostic or remove it is decided then, by a superseding ADR.
- **[OPEN]** The open questions that can explain a difference in the parallel run: whether
  Parqet applies FIFO per sub-depot or per portfolio, how it values a TransferIn, and whether
  its portfolio holds every Verrechnungskonto depotbuch tracks.
