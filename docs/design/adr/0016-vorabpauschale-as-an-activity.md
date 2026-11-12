---
created: 12.11.2026 16:40
type: adr
status: Proposed
tags:
  - adr
  - engine
  - domain-model
---
# 0016. The Vorabpauschale is an activity, not income

## Context

German tax law taxes an accumulating or low-distributing fund every January on a
*Vorabpauschale*: a notional income for the past year, computed from the Basiszins and the
fund's prices at the start and end of that year (§18 InvStG). The provider sends a notice
with its gross amount and withholds tax on it from the cash account, unless the allowance
covers it. No money flows from the fund, and the units don't change. When the fund is later
sold, the Vorabpauschale already taxed on the units sold reduces the taxable gain.

Proposal 0001 defines income as dividends, distributions and interest, and a flow as value
crossing a slice's edge. It does not mention the Vorabpauschale. The first real history
examined (proposal 0002) holds Vorabpauschale notices for its funds, with and without tax
withheld.

## Decision

We will store a Vorabpauschale as an activity of its own (`vorabpauschale`) on the fund,
carrying the gross amount from the provider's notice (`amount`) and the tax withheld on it
as its cash (`cash`, zero or negative):

- The engine MUST NOT compute the Vorabpauschale. That needs the Basiszins and the fund's
  year-start and year-end prices, and the provider's notice is what was taxed.
- The amount is neither income nor a flow, and it never changes a lot's cost or units.
- The tax withheld on it is a tax of that fund, like the tax on a dividend: for the fund
  alone it is return paid across the edge (R, negative), and in the taxes figure of the
  fund, its account and its provider.
- The amount is stored so that a later sale's taxable gain can be reduced by the
  Vorabpauschale already taxed on the units sold. depotbuch computes no German tax
  liability; the private reconciliation uses the amounts to check FIFO against the bank's
  taxable gains.

We reject booking it as income (no money is received, and income figures would no longer
match the provider's distribution notices), as an increase of the lot's cost (it is not
part of the acquisition cost, and invested capital would no longer be the cash paid), and
computing it in the engine.

## Consequences

- Income and invested capital stay what the statements show; the tax shows where the
  provider withheld it, on the fund.
- A slice that holds the fund but not the cash account sees the withheld tax as a negative
  return in January, when the bank books it, which matches the provider's statements.
- Importers need a source for the notices: Consorsbank sends them as PDFs, and neither OFX
  nor the Parqet CSV carries them. Without a notice, the tax shows as a tax booking without
  an asset, on the provider.
- If depotbuch ever computes German tax, the stored amounts are its input; this record is
  superseded only if the engine is to compute the amount itself.
