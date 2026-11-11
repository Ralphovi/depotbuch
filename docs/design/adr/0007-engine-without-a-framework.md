---
created: 11.11.2026 03:11
type: adr
status: Proposed
tags:
  - adr
  - architecture
  - engine
---
# 0007. The calculation engine has no framework dependency

## Context

depotbuch's figures come from one calculation engine: lots, valuation, TTWROR, IZF,
trade-to-cash matching and tax attribution (proposal 0001, *Calculations*). The CLI, the
JSON API, the web front end and the HTML report all show its results, and they must never
disagree (architecture §1.2).

Autobook reads the same ofxstatement output, and proposal 0001 expects that it may take the
engine over later without changing its inputs. Autobook does not use Django. The engine's
correctness is goal 1 (architecture §1.3), and it is proven against hand-computed cases and
Hypothesis property tests, which are simplest without a database or a web framework.

## Decision

We will keep the engine (`src/depotbuch/engine/`) in plain Python: `decimal.Decimal` for
money and quantities, pydantic types for its inputs and outputs. It takes activities,
prices and FX rates and returns results. It MUST NOT import Django, Django Ninja or any
other web or ORM framework, and neither MAY the adapters (`src/depotbuch/adapters/`).

Django models store only what the engine reads; the web layer and the CLI convert between
models and engine types. Every interface calls the same engine, so a figure is computed in
one place only.

The rule is enforced in the gate twice: ruff's banned-API rule (TID251) rejects a direct
import, and `tests/test_boundaries.py` imports both packages in a fresh interpreter and fails
if either framework was loaded.

## Consequences

- The engine can be tested without a database, and Autobook can import it unchanged.
- The CLI, the API and the front end cannot disagree, because none of them computes.
- A conversion layer between Django models and engine types is extra code to write and
  test; it is the price of the boundary.
- A float reaching a monetary amount would break the promise; the engine's types make
  `Decimal` the only path.
