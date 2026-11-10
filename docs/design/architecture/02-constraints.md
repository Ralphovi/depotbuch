---
created: 10.11.2026 19:03
type: architecture
status: living
tags:
  - architecture
---
# 2. Constraints

> Living document. What the design must work within; the decisions that follow from these are the ADRs. Open questions are marked **[OPEN]** inline.

## 2.1 Technical constraints

| Constraint | Source |
|------------|--------|
| Linux first. | Proposal 0001, non-functional requirements |
| Python 3.11 or later; the test matrix covers 3.11 to 3.14. | Proposal 0001 |
| All broker and bank data enters through ofxstatement (in-process plugins or OFX files), plus a one-time Parqet CSV migration and manual entry. A statement is parsed one way for GnuCash, Autobook and depotbuch. | Proposal 0001, *Data ingestion* |
| Depot statements arrive as `statement.invest_lines` (ofxstatement 0.9 or later), with the ISIN as `security_id` and the settlement currency as `statement.currency`. | Proposal 0001, plugin contract |
| Works offline after `depot update`. The only network calls go to the configured price and FX providers. | Proposal 0001 |
| Price data must not cost as much as Parqet Plus: yfinance now, Interactive Brokers later. Yahoo's data is for personal use only. | Proposal 0001, *Market data* |
| Money is computed with `decimal.Decimal`, never binary floats. | Proposal 0001, *Architecture* |
| Storage: SQLite by default, PostgreSQL as an option; one database per installation. | Proposal 0001 |
| Runs as a container on the owner's homelab, behind TLS, login required, reachable from desktop and phone. | Proposal 0001 |
| The engine has no Django imports, so Autobook can take it over without changing its inputs. | Proposal 0001 |

## 2.2 Organizational constraints

- **One maintainer**, helped by coding agents working under `AGENTS.md`. Agents never merge
  and never accept a design document.
- **License: GPL-3.0-or-later.** Every dependency (Django, Django Ninja, pydantic, yfinance,
  ofxstatement, the front-end libraries) must be GPL-compatible. ADR-0002 records the
  license and the DCO.
- **Separate from Autobook.** Own repository (`Ralphovi/depotbuch`) and own Drive project
  with a context doc.
- **Deadline.** None, but the parallel run needs one full month with both tools running, and
  Parqet Plus is paid for until it passes.
- **Plugin work happens in other repositories** (`ofxstatement-consorsbank`, `-scalable`,
  `-revolut`). Until a plugin emits investment lines, that provider's new trades need manual
  entry or a fresh Parqet export.

## 2.3 Conventions

- Design documents follow `docs/design/README.md`: ADRs for settled decisions (ADR-0001),
  proposals and specs through draft and accepted (ADR-0003), supersession instead of edits
  (ADR-0004). This overview is living and is updated in the same PR as any change to the
  system's structure.
- A change that adds an untrusted input or moves a trust boundary updates §14 and
  `.oss-scanner/threat_model.md` in the same PR.
- Every PR links an issue, every commit is signed off (DCO), and the required checks in
  `.github/required-checks.txt` must pass.
- One gate command, `nox -s gate`, runs every check locally and in CI (§8.8).
- Every calculation rule has a hand-computed test case, in both the default and the
  Parqet-compatible mode.
- Front-end work starts as a design proposal in the repo.
