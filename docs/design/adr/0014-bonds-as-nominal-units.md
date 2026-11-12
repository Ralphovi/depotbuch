---
created: 12.11.2026 03:10
type: adr
status: Proposed
tags:
  - adr
  - engine
  - domain-model
---
# 0014. Bonds: the nominal amount as units, accrued interest in the cost

## Context

Bonds are quoted in percent of their nominal amount, not per unit, and a statement books a
bond trade as a nominal amount (`EUR 1.000,00` rather than a share count) at a price such as
`118,659 %`. A bond bought between coupon dates also pays the seller the interest accrued
since the last coupon (*Stückzinsen*); a bond sold between coupon dates receives it. The
first real history examined (proposal 0002) holds such a purchase and its coupons.

Proposal 0001 values a security as units × close and defines invested capital as the FIFO
cost of the units held, including purchase fees. It says nothing about bonds. OFX carries a
bond trade as `BUYDEBT` or `SELLDEBT` with the nominal amount in `UNITS`, the percent price
in `UNITPRICE` and the accrued interest in `ACCRDINT`, already included in `TOTAL`.

## Decision

We will treat a bond as a security whose units are its nominal amount:

- A bond trade is an ordinary buy or sale. `units` is the nominal amount, and FIFO lots,
  invested capital and realized gains work as for any security.
- Its value is nominal × price / 100, with the price in percent (architecture §8.2).
- Accrued interest paid on purchase is part of the buy's cash amount, and so of the lot's
  cost and of invested capital. Accrued interest received on a sale is part of the sale's
  cash amount, and so of its realized gain. A coupon is income on its payment date.

We reject a separate bond position type with its own rules. The difference between a bond
and a share is the price quotation, which only valuation needs to know.

## Consequences

- Bonds need no code path of their own in lots, gains or flows; only valuation reads the
  asset's kind.
- Paid accrued interest shows as cost rather than as the negative income German tax treats
  it as. That stays an open question in proposal 0002; if depotbuch is to show it as
  income, a later ADR supersedes this one and the cost moves to an income line.
- A bond that is redeemed is a sale at 100 %; a partial redemption reduces the nominal
  units, and neither needs a new activity type.
