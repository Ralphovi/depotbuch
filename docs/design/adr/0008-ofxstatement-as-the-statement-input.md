---
created: 11.11.2026 03:11
type: adr
status: Proposed
tags:
  - adr
  - import
  - adapters
---
# 0008. Statements enter as OFX, through ofxstatement plugins

## Context

depotbuch needs broker and bank statements from Consorsbank, Revolut, Scalable and the
banks holding Tagesgeld and Festgeld. The same statements also go into GnuCash, and
Autobook reads them through ofxstatement. Writing a second parser per statement would
mean two implementations that can disagree on the same file.

ofxstatement plugins exist for all three brokers, maintained in this organization, but
they emit bank lines only and none emits investment lines yet (proposal 0001, *Existing
plugins*). Fetching statements automatically (broker APIs, autosync) is a non-goal.

## Decision

We will read every bank and broker statement as OFX, through one OFX parser in the adapters.
A statement in any other format (PDF, a bank's CSV) MUST come through an ofxstatement
plugin: `depot import -t <section> <file>` loads the plugin from the user's ofxstatement
configuration in-process, renders the statement with ofxstatement's own `OfxWriter`, and
parses that OFX. A statement the bank already delivers as OFX is read directly, since it is
the format the plugins produce. The Parqet CSV export is the one other import path, a
one-time migration of the existing history. Manual entry (`depot add`) covers anything
without a statement.

Depot statements MUST fill `statement.invest_lines` (ofxstatement 0.9 or later), with the
ISIN as `security_id` and the settlement currency as `statement.currency`. The missing
investment parsers are written in the plugin repositories, not in depotbuch.

We reject depotbuch-specific parsers for a bank's own formats (its PDFs and CSVs), which
would duplicate the plugins, and broker APIs.

## Consequences

- One parser per statement serves GnuCash, Autobook and depotbuch; a fix lands once.
- Plugins run in-process with the server's rights. This is accepted in the threat model
  (§14.8) because the plugins are the owner's own; a statement file that makes a plugin run
  code is still in scope.
- Loading GPL v3 ofxstatement in-process is part of why depotbuch is GPL-3.0-or-later
  (ADR-0002).
- Until each plugin emits investment lines, new trades from that broker need manual entry
  or a fresh Parqet export. **[OPEN]** The plugin work order (Scalable, then Consorsbank,
  then Revolut?) is an open question in proposal 0001.
