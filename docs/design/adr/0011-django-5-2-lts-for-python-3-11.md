---
created: 11.11.2026 03:11
type: adr
status: Proposed
tags:
  - adr
  - architecture
  - dependencies
---
# 0011. Django 5.2 LTS, to keep Python 3.11

## Context

The spec requires Python 3.11 or later (proposal 0001, *Non-functional requirements*),
matching Autobook, which may take over depotbuch's engine. When the scaffold was set up in
November 2026, the newest Django release line, 6.x, required Python 3.12 or later. Django 5.2
is a long-term support release that supports Python 3.11 to 3.14 and receives security fixes
until April 2028. The matching type stubs, django-stubs 5.2, support mypy below 1.20 only.

## Decision

We will use Django 5.2 LTS (`Django>=5.2,<5.3`) with django-stubs 5.2, and pin mypy to the
newest release below 1.20. CI tests Python 3.11, 3.12, 3.13 and 3.14.

We reject Django 6.x, which would drop Python 3.11 and break the spec's floor.

## Consequences

- The whole supported Python range is tested, and Autobook's interpreter range is kept.
- mypy stays below 1.20 for as long as django-stubs 5.2 does, so newer mypy checks wait.
- The move to the next Django LTS comes when Python 3.11 is dropped or Django 5.2's support
  ends in April 2028, whichever is first; it is a superseding ADR, not an edit of this one.
  The engine does not depend on Django (ADR-0007), so the move touches only the web layer
  and the CLI.
