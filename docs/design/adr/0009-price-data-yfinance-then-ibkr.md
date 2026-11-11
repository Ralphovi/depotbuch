---
created: 11.11.2026 03:11
type: adr
status: Proposed
tags:
  - adr
  - market-data
  - adapters
---
# 0009. Price data: yfinance now, Interactive Brokers later, behind one provider interface

## Context

Securities are valued from daily closes, splits and FX rates. depotbuch must cover German
listings, including ETFs and funds, for step 1, at a cost well below Parqet Plus (11.99 € a
month as of September 2026), which is what it replaces.

Proposal 0001 (*Market data*) compares the candidates. yfinance is free and covers German
listings, but it is an unofficial client of Yahoo's public endpoints, and Yahoo's data is
for personal use only. Alpha Vantage, Twelve Data, Marketstack and EODHD have free tiers
that are US-centred or too small, and their paid plans with European data cost about as
much as Parqet Plus or more. Interactive Brokers gives licensed exchange data to an
account holder: one month of Level 1 subscriptions backfills history, and the free
previous-day close keeps it current, given an invested position that keeps the existing
account above the USD 500 equity minimum.

## Decision

We will use yfinance as the price provider for step 1 and replace it with Interactive
Brokers as the primary source later. Prices, splits and FX go through one provider
interface in the adapters, with the provider chosen per security, so switching a security
needs no change elsewhere. A manual CSV provider covers anything neither source has. FX
rates come from the ECB unless a statement gives the broker's rate.

Closes are adjusted for splits but not for dividends, since dividends are booked as
activities. Updates are incremental, from the newest stored date minus 7 days.

We reject Alpha Vantage, Twelve Data, Marketstack and EODHD on coverage and cost.

## Consequences

- Step 1 runs at no data cost. Yahoo's personal-use condition matches a tool that one
  owner runs for themselves; depotbuch must not be offered as a hosted service on this data.
- yfinance has no integrity guarantee and can break when Yahoo changes its endpoints.
  Reports flag a security whose newest close is older than 5 days, and a held asset is never
  valued at zero for missing data. The missing plausibility check on price jumps is a known
  gap in the threat model (architecture §14).
- The provider interface is extra structure for one provider today; it is what makes the
  IBKR switch cheap.
- **[OPEN]** What IBKR charges for German Level 1 data, and how many years of daily history
  one month of subscription returns (proposal 0001, *Open questions*).
