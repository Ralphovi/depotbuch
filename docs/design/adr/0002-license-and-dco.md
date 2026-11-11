---
created: 10.11.2026 19:03
type: adr
status: Proposed
tags:
  - adr
  - governance
  - licensing
---
# 0002. GNU General Public License v3.0 or later and DCO sign-off

## Context

depotbuch is public, and its users are individuals who run it on their own server with
their own financial data. Users need a clear license, and the project needs to know it may
use what contributors send, without paperwork that deters small contributions.

The license is largely set by a dependency. All broker data enters through ofxstatement
(proposal 0001, *Data ingestion*): `depot import` loads the user's ofxstatement plugins
in-process and renders statements with ofxstatement's own writer. ofxstatement is licensed
under the GPL v3, and so are the Consorsbank and Scalable plugins depotbuch reads first;
the Revolut plugin declares GPL v3 in its package metadata. Importing them into the same
process makes depotbuch's distribution a GPL v3 matter.

The version still matters. Apache-2.0 is compatible with GPL v3 but not with GPL v2, and
depotbuch's price provider for step 1, yfinance, is Apache-2.0; its other dependencies are
BSD and MIT (Django, Django Ninja, pydantic). Autobook, which may take over depotbuch's engine, is
GPL-3.0-or-later as well.

## Decision

depotbuch is licensed under the **GNU General Public License v3.0 or later** (`LICENSE`).
The whole repository carries it; there is no split between a permissive engine and a GPL
importer. Every dependency MUST be compatible with GPL v3: Apache-2.0, MIT and BSD are;
GPL-2.0-only is not.

Contribution provenance is tracked with the **Developer Certificate of Origin** (DCO, the
`DCO` file), not a Contributor License Agreement (CLA). Each commit carries a
`Signed-off-by:` line (`git commit -s`) certifying the contributor has the right to submit
it. Contributions are licensed inbound under the same license as outbound.

We choose the DCO because a CLA's friction falls on exactly the occasional contributors a
public project wants, and because the main thing a CLA adds, the right to relicense
contributions later, is a power this project chooses not to hold.

## Consequences

- No signing step for contributors; every commit needs a sign-off, and the `dco` check
  fails a pull request with an unsigned commit.
- Every contributor keeps their copyright, so the project cannot later be relicensed
  without their agreement.
- Third-party material shipped with the project keeps its own license.
- Apache-2.0 dependencies such as yfinance stay available; a GPL-2.0-only dependency does
  not. A new dependency is checked against this before it is added.
- Autobook can take over the engine without a license change, since both are
  GPL-3.0-or-later.
- Anyone distributing a modified depotbuch must ship its source under the same terms. For a
  tool individuals run on their own server, this costs little and keeps the code that
  computes their figures inspectable.
