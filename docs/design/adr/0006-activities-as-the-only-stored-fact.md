---
created: 11.11.2026 03:11
type: adr
status: Proposed
tags:
  - adr
  - domain-model
  - storage
---
# 0006. Activities are the only stored fact about a position

## Context

A portfolio tracker can store either what happened (buys, sales, dividends, transfers) or
what results from it (holdings, lots, cost bases, running values). Stored results go stale
whenever an earlier fact changes: a statement re-imported with a correction, a missing
activity found later, a split, or a change of realized-gain method from FIFO to average
cost. Each such change then needs a migration or a rebuild that can itself go wrong, and
two figures computed at different times can disagree.

depotbuch's headline promise (architecture §1.2) is that every figure is right and can be
reproduced from the database and an as-of date. Imports must be idempotent and must never
drop or double a row silently (proposal 0001, *Data ingestion*). Its data volume is small:
10 years of history and 100 assets, with reports in under 2 s (proposal 0001,
*Non-functional requirements*).

## Decision

We will store activities as the only fact about a position. An activity is identified by
its account and `FITID` (for Parqet CSV rows, a hash of the row plus its occurrence number).
Holdings, lots, values, invested capital, realized gains, income, taxes, TTWROR and IZF are
derived on demand by the engine from activities, market data (closes, splits, FX rates) and
contract valuations. They MUST NOT be stored as facts.

Besides activities, depotbuch stores only inputs the engine reads: accounts and their
configuration (provider, asset type, Festgeld terms), assets with their ISIN mapping and
price provider, market data, and valuations for pension contracts.

We reject storing holdings or lots: they would have to be kept in step with every
correction, and a method change would become a migration.

## Consequences

- Re-imports, corrections and a switch from FIFO to average or LIFO need no migration; the
  next report simply reflects them.
- Every report can be rebuilt from the database and an as-of date, which is what makes the
  parallel run against Parqet and the hand-computed test cases meaningful.
- Reports recompute from all activities each time. That is cheap at the stated volume; if
  the 2 s budget is ever missed, a cache MAY be added, but it stays a cache that can be
  dropped and rebuilt, never a second source of truth.
- Identity rules for activities become critical: a wrong `FITID` or row hash silently
  doubles or drops a fact, so import identity is covered by tests from M2 on.
