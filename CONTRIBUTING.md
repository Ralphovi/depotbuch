# Contributing to depotbuch

Thanks for contributing. Read the
[shared contributing guide](https://github.com/Ralphovi/.github/blob/main/CONTRIBUTING.md)
first. It covers when to open an issue before writing code, what won't be merged, and the
rules for AI-assisted changes. This file adds what is specific to depotbuch.

This project is licensed under the GNU General Public License v3.0 or later ([LICENSE](LICENSE)); contributions
are accepted under the same license.

## Developer Certificate of Origin (sign-off)

Every commit must carry a [Developer Certificate of Origin](DCO) (DCO 1.1) sign-off. By
signing off you certify the DCO's terms for your contribution. Sign off with:

```bash
git commit -s
```

This appends a `Signed-off-by: Your Name <you@example.com>` trailer (using your
`git config user.name` / `user.email`). Amend a commit that's missing it with
`git commit --amend -s`. The `dco` check fails a PR with an unsigned commit.

## Pull requests

- **Every pull request links an issue**, typo and docs fixes included: `Closes #NNN`, or
  `Refs #NNN` for partial work, in the description. This project is stricter than the
  shared guide here; the required `require-linked-issue` check fails a PR without one.
  For a small fix, a one-line issue is enough. Dependabot's PRs are exempt.
- One logical change per PR; split unrelated changes.
- A change ships with the means to verify it: a test, or a stated reason why a test is
  impractical plus a manual repro.
- A change to the system's structure updates the architecture overview in the same PR. A
  settled design question becomes an ADR. See [`docs/design/README.md`](docs/design/README.md)
  for which document class to use; accepted ADRs and proposals and stable specs are never
  edited, only superseded. To propose a decision, follow
  [How an ADR is made](docs/design/adr/README.md#how-an-adr-is-made).

## Issues

New issues are triaged by the rules in [ADR-0005](docs/design/adr/0005-issue-priority-and-automated-triage.md):
severity and reach set a `priority:P0`–`P3` label. If automated triage is set up, a bot
labels the issue and posts its reasons; a maintainer makes the final call and sets the
milestone. Report security problems privately (see [SECURITY.md](SECURITY.md)).

## Running checks

One command runs every check:

```bash
nox -s gate          # or just `nox`
```

It checks formatting and lint (ruff), types (`mypy --strict` with django-stubs), runs
Django's system checks, the migrations check and the tests (pytest, Hypothesis) on the
interpreter running nox, and then typos and the docs checks. `nox -s fmt -- --fix` rewrites
formatting. Install nox with `python3 -m pip install --user nox`, and
[typos](https://github.com/crate-ci/typos) for the spell check (the session warns and skips
without it; CI always runs it).

The required `gate` job in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs the
same command. The `test-matrix` jobs run the tests on every supported Python
(`nox -s test-3.11` and so on).

Engine figures are checked against hand-computed cases in `tests/engine/cases/` (the TOML
format is described in `src/depotbuch/testing/casefile.py`). The maintainer also checks
them against a private corpus of real statements with `nox -s reconcile -- <path>`. That
session is not part of the gate, never runs in CI, and needs nothing from contributors
(proposal 0002).

The engine (`src/depotbuch/engine/`) and the adapters (`src/depotbuch/adapters/`) never
import Django or Django Ninja: ruff's banned-api rule and `tests/test_boundaries.py` fail
the gate if they do.

The status checks `main` requires are listed in
[`.github/required-checks.txt`](.github/required-checks.txt). A maintainer can see whether
the repo's settings and branch protection still match it, and the rest of the settings
the project expects, with `python3 -I scripts/repo-settings.py check`; `apply` restores
them.
