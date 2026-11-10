# Contributing to {{PROJECT_NAME}}

Thanks for contributing. Read the
[shared contributing guide](https://github.com/{{OWNER}}/.github/blob/main/CONTRIBUTING.md)
first. It covers when to open an issue before writing code, what won't be merged, and the
rules for AI-assisted changes. This file adds what is specific to {{PROJECT_NAME}}.

This project is licensed under the {{LICENSE_NAME}} ([LICENSE](LICENSE)); contributions
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

_TODO: name the single command that runs every check._ The required `gate` job in
[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs the same command; until it is
set up, `gate` fails every pull request.

The status checks `main` requires are listed in
[`.github/required-checks.txt`](.github/required-checks.txt). A maintainer can see whether
the repo's settings and branch protection still match it, and the rest of the settings
the project expects, with `python3 -I scripts/repo-settings.py check`; `apply` restores
them.
