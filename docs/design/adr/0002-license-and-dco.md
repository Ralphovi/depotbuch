---
created: {{DATE}}
type: adr
status: Proposed
tags:
  - adr
  - governance
  - licensing
---
# 0002. {{LICENSE_NAME}} and DCO sign-off

> **How to fill this in:** `init-repo.sh` set the license name from your choice. Add a
> sentence to *Context* saying who the users are and why this license suits them (wyrd's
> example: commercial providers need a permissive license with a patent grant). If the
> project depends on components at pluggable seams, consider adding dependency-selection
> criteria as wyrd does in
> [ADR-0003](https://github.com/getwyrd/wyrd/blob/main/docs/design/adr/0003-apache-2-license-and-dco.md).
> It starts as **Proposed** so you can edit it: fill it in, delete this block, and set
> `status: Accepted` (and update the index) in one pull request. After that it is frozen.

## Context

{{PROJECT_NAME}} is public. Users need a clear license, and the project needs to know it may
use what contributors send, without paperwork that deters small contributions.

## Decision

{{PROJECT_NAME}} is licensed under the **{{LICENSE_NAME}}** (`LICENSE`).

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
