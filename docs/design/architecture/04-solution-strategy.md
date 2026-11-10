---
created: 10.11.2026 19:03
type: architecture
status: living
tags:
  - architecture
---
# 4. Solution strategy

> Living document. The shape of the solution and why. Open questions are marked **[OPEN]** inline.

## 4.1 The shape in one paragraph

Statements come in through ofxstatement and become **activities**, the only fact depotbuch
stores about a position (§8.1). A pure-Python **engine** recomputes everything else from
activities, prices and FX rates on demand: holdings, FIFO lots, values, taxes, TTWROR and
IZF, for any slice and range (§8.2–§8.5). **Adapters** turn the outside world (plugins, OFX,
Parqet CSV, yfinance, ECB) into engine types. A **Django** backend stores activities and
market data, offers an admin, and serves the engine's results as a JSON API with Django
Ninja; the `depot` **CLI** runs as Django management commands over the same engine, and a
**TypeScript front end** draws the seven views from that API. Because every interface calls
the same engine, the CLI, the API, the web views and the HTML report cannot disagree.

## 4.2 Key strategies

| Problem | Strategy | ADR |
|---------|----------|-----|
| Re-imports, corrections and method changes (FIFO to average) should not need migrations. | Store activities only; derive holdings, lots and every report. | **[OPEN] to record as ADR** |
| Autobook should be able to take over the engine; the numbers must be testable without a database. | Engine in plain Python with `Decimal` and pydantic types and no Django imports, enforced by a lint rule (ruff TID251 bans `django` outside `web/` and the CLI). | **[OPEN] to record as ADR** |
| One parser per statement for GnuCash, Autobook and depotbuch. | All broker data through ofxstatement plugins; investment activity as `invest_lines`. | **[OPEN] to record as ADR** |
| Prices for German listings without paying as much as Parqet Plus. | yfinance now; Interactive Brokers later as primary source; one provider interface chosen per security; manual CSV as fallback. | **[OPEN] to record as ADR** |
| A web UI, an admin, an API and a CLI for one person, with little code. | Django + Django Ninja backend (OpenAPI), TypeScript SPA with a generated API client, CLI as management commands. | **[OPEN] to record as ADR** |
| Python 3.11 support (spec) while Django 6 needs 3.12 or later. | Django 5.2 LTS. | **[OPEN] to record as ADR** |
| Agreeing with Parqet for the parallel run while showing after-tax figures by default. | A `--parqet` mode that follows Parqet's FAQ on taxes and fees; used only for the parallel run. | **[OPEN] to record as ADR** |
| Trades appear twice: as investment activity and as a cash line. | Match each trade to its cash line by provider, amount and up to 3 business days; report unmatched lines. | Part of the calculation rules (proposal 0001) |

ADR-0001 to ADR-0005 cover the project's process (decision records, license and DCO,
proposals and specs, supersession, issue triage); none of the product decisions above is
recorded yet.

## 4.3 Build strategy

The engine comes first and is proven against hand-computed cases before any import or UI
exists, because correctness is goal 1 and every interface sits on top of it. The Parqet CSV
import comes next: it brings in the whole history at once and is the reference for the
parallel run. Market data, storage and the CLI views follow, then the plugin work that lets
new statements flow in, then the web API and front end. Acceptance is the parallel-run month;
pension contracts are step 2. §9 lists the milestones; the scope is proposal 0001 (PR #3).
