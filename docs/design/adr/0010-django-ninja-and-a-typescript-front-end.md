---
created: 11.11.2026 03:11
type: adr
status: Proposed
tags:
  - adr
  - architecture
  - web
---
# 0010. Django with Django Ninja, a TypeScript front end, and the CLI as management commands

## Context

depotbuch has one user but needs several interfaces: a CLI that covers every feature, a
web front end reachable from desktop and phone, an admin for accounts, Festgeld terms,
valuations and corrections, and login behind TLS on the homelab (proposal 0001,
*Interfaces*). It also needs storage with migrations, SQLite by default and PostgreSQL as
an option. The project is maintained by one person, so the stack should bring these
pieces with little code of its own, in Python, where the engine and the adapters live.

## Decision

We will build the backend on Django: storage through its ORM and migrations, login, and the
admin for configuration and corrections. The JSON API uses Django Ninja, which publishes an
OpenAPI schema from typed endpoints. The CLI, `depot`, is a thin entry point over Django
management commands, so every command runs against the same engine as the API (ADR-0007).
The front end is a TypeScript single-page app whose API client is generated from the
OpenAPI schema; the static HTML report from `depot report` remains as an offline export.

We reject a separate API framework beside Django (two stacks for one user) and a
server-rendered front end (the spec asks for interactive charts on desktop and phone).

## Consequences

- Login, sessions, admin, migrations and SQLite or PostgreSQL come with Django rather than
  being written.
- The CLI and the API share settings, storage and engine, so their numbers cannot differ.
- The front end's client cannot drift from the API, because it is generated from the schema.
  The schema is behind the admin login (threat model §14.2), so generation runs at build
  time against the code, not against a running server.
- Django's release cycle sets the Python floor; see ADR-0011.
- **[OPEN]** Which OpenAPI client generator and which front-end framework; both are decided
  with the front-end design proposal (spec, *Interfaces*: front-end work starts as a design
  proposal).
