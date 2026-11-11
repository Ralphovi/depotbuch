---
created: 10.11.2026 19:03
type: architecture
status: living
tags:
  - architecture
---
# 10–13. Quality, risks, glossary, and testing strategy

> Living document. Combines arc42 sections 10 (quality scenarios), 11 (risks and technical debt) and 12 (glossary), plus the testing strategy (section 13). Open questions are marked **[OPEN]** inline.

## 10. Quality scenarios

| Scenario | Measurable outcome | Goal |
|----------|--------------------|------|
| Parallel run, dividends per security and year | Equal to Parqet to the cent | 1 Correctness |
| Parallel run, realized gain per sale (FIFO) | Equal to the cent | 1 |
| Parallel run, invested capital per position | Equal to the cent | 1 |
| Parallel run, value per position on the same close | Within 0.01 € | 1 |
| Parallel run, TTWROR YTD, total and per position | Within 0.1 percentage points | 1 |
| Parallel run, IZF, total and per position | Within 0.1 percentage points | 1 |
| Default after-tax figures | Equal to the hand-computed case for every calculation rule | 1 |
| A trade and its cash line are both imported | The cash line is counted once; unmatched lines are listed | 1 |
| The same statement is imported twice | Second import adds nothing, every row reported as skipped | 2 Reproducibility |
| A report is rerun with the same database and as-of date | Identical output | 2 |
| The same figure in CLI, API and HTML report | Identical, since all call the engine | 2 |
| `depot update` has run, then the network is cut | Every report still works | 3 Privacy, 4 |
| A month of statements from all providers | Imported with no manual entry once the plugins emit investment lines | 4 Low effort |
| Report for 10 years of history and 100 assets | Finishes in under 2 s | 5 Performance |
| The engine is imported without Django installed | Imports and runs | 6 Reusability |

Deposits are left out of the Parqet comparison, because the Parqet portfolio may not hold
them. A difference beyond tolerance must be explained by an open question, or it is a defect.

## 11. Risks and technical debt

| Risk | Nature | Mitigation |
|------|--------|------------|
| yfinance breaks or Yahoo changes its endpoints | Unofficial library over public endpoints; personal-use terms | One price-provider interface per security; manual CSV fallback; IBKR planned as primary source; stale-data flags. |
| Plugins do not emit investment lines yet | All three plugins read cash accounts only | Parqet CSV covers history; manual entry or fresh Parqet export until each plugin is done (M5). |
| Parqet's exact method is unknown in places | FIFO scope, cash accounts in the Parqet portfolio | Open questions in §8.3 and §8.5; parallel-run differences must be explained by them. |
| Trade-to-cash matching mismatches | Same amount, close dates | Matching by provider, amount and a 3-business-day window; unmatched lines reported, never dropped. |
| Silent wrong numbers | Every figure is derived; a bug spreads everywhere | Hand-computed cases per rule in both modes, Hypothesis invariants, the parallel run. |
| Django 5.2 LTS ends support in April 2028 | Chosen for Python 3.11 | Move to the next LTS once 3.11 is dropped; the engine does not depend on Django. |
| Report speed with everything recomputed | Derived-only model | Performance scenario in §10; caching only if measured necessary. **[OPEN]** |
| Domain-model diagram reconstructed | Original lost in export | Confirm against the models in M1/M4. |

## 12. Glossary

| Term | Meaning |
|------|---------|
| Activity | One stored fact: buy, sell, dividend, interest, transfer, fee, split, deposit, withdrawal, contribution. |
| Abgeltungsteuer | German flat tax on capital income, with Soli and church tax on top. |
| bAV | Betriebliche Altersversorgung: occupational pension (step 2). |
| Festgeld | Fixed-term deposit; valued at principal plus daily accrued interest. |
| FIFO | First in, first out: sales close the oldest lots first, within one account. |
| FITID | The OFX transaction ID; with the account, an activity's identity. |
| Holding | An asset's units, value and figures on a day, derived. |
| ISIN | International Securities Identification Number; the security key. |
| IZF | Interner Zinsfuß: annualized internal rate of return. |
| Lot | Units bought in one buy or delivery in, tracked until sold. |
| ofxstatement | Tool and plugin system that converts bank statements to OFX; the shared input of GnuCash, Autobook and depotbuch. |
| OFX | Open Financial Exchange, the statement format; `INVSTMTRS` is its investment statement. |
| Parqet-compatible mode | `--parqet`: Parqet's treatment of taxes and fees, for the parallel run only. |
| Position | An asset across all accounts. |
| Provider | A bank or broker: Consorsbank, Revolut, Scalable, the deposit banks. |
| Riester, Rürup | German subsidized pension contracts (step 2). |
| Slice | The set of holdings a figure covers: the portfolio, a provider, an account, an asset class or one asset. A booking is a flow for a slice only if it crosses the slice's edge (§8.4). |
| Tagesgeld | Instant-access savings account; valued at its balance. |
| TTWROR | True time-weighted rate of return: chained daily sub-period returns, never annualized. |
| Verlustverrechnung | Annual loss offsetting by the bank; its tax effect is attributed to the provider. |
| Verrechnungskonto | A broker's cash account; an asset valued at its balance. |
| Wertpapierabrechnung | A trade or dividend confirmation from the broker. |
| WKN | German securities code; mapped to an ISIN once. |
| Zulage | State allowance paid into a Riester contract (step 2). |

## 13. Testing strategy

**Principle: every number is checked against a number a person computed.** Correctness is
goal 1, and the engine is pure, so most testing happens at the engine with no database.

| Tier | What | Starts |
|------|------|--------|
| Hand-computed cases | One case per calculation rule (valuation, Festgeld accrual, FIFO lots, dividend split across lots, splits, TTWROR, IZF, tax attribution, cash accounts, matching), each in default and `--parqet` mode. | M1 |
| Property tests (Hypothesis) | Invariants: lots sum to holdings; no cash line counted twice; TTWROR independent of how a range is split; re-import adds nothing. | M1 |
| Parser tests | Synthetic statements, OFX and Parqet CSV fixtures: mapping table, identity, rejected rows, per-row report. Never real statements. | M2 |
| Integration tests | Django models, management commands and API endpoints against SQLite; CLI and API return the same figures. | M4 |
| Performance check | Synthetic 10-year, 100-asset portfolio under 2 s. | M4 |
| Front-end tests | **[OPEN]** Chosen with the front-end design proposal. | M6 |
| Parallel run | One month against Parqet within the §10 tolerances. | M7 |

All tiers up to integration run in `nox -s gate`; CI runs them on Python 3.11 to 3.14.
