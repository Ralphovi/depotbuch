---
created: 10.11.2026 19:03
type: architecture
status: living
tags:
  - architecture
---
# 7. Deployment view

> Living document. Where it runs. Open questions are marked **[OPEN]** inline.

## 7.1 What the user gets

One container on the owner's homelab, holding the Django backend (API, admin, login), the
built front end and the `depot` CLI. It is reachable from desktop and phone over HTTPS, with
a login required. The database is SQLite by default, in a volume next to the container;
PostgreSQL is an option. There is one database per installation and one user.

| Piece | Detail |
|-------|--------|
| Container | Python 3.11 or later, the `depotbuch` package, the ofxstatement plugins the owner configures, the built front end. |
| Database | SQLite file in a persistent volume, or a PostgreSQL server. |
| TLS | In front of the container. **[OPEN]** Terminated by an existing homelab reverse proxy or inside the container? |
| CLI | `depot` inside the container (or a local install against the same database). Statement files reach it by a mounted directory or upload. **[OPEN]** Which, decided with the deployment milestone. |
| Outbound network | Only to the configured price and FX providers (Yahoo, ECB; later IBKR through TWS or IB Gateway). Everything else works offline after `depot update`. |
| Backups | The database is the only state to back up; every report can be rebuilt from it. **[OPEN]** Backup schedule and target. |

The static HTML report from `depot report` is a single file the owner can keep or open
offline.

## 7.2 Test matrix

| Dimension | Covered |
|-----------|---------|
| Python | 3.11, 3.12, 3.13, 3.14 (CI test matrix); the gate itself runs on one interpreter. |
| OS | Linux (Ubuntu runners in CI). Linux-first; nothing else is tested. |
| Database | SQLite in CI. **[OPEN]** PostgreSQL in CI once the option is offered. |
| Django | 5.2 LTS, the line that supports Python 3.11. |

## 7.3 Development environment

- A Linux machine with Python 3.11 or later and `nox`; `nox -s gate` runs every check.
- `typos` installed for the spell check (CI installs a pinned release).
- Node.js for the front end, once `frontend/` exists.
- No real statements or financial data in the repository or in test fixtures; tests use
  synthetic and hand-computed data.
