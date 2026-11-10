# Agent context — {{PROJECT_NAME}}

Rules for any coding agent (Claude, Codex, or other) working **on this repository**.
[CONTRIBUTING.md](CONTRIBUTING.md) governs humans and agents alike; this file adds the
agent-specific discipline.

## STOP discipline — the merge is never yours

- **Never merge a pull request.** Not `gh pr merge`, not the web UI, not
  auto-merge — no path, regardless of green checks or how trivial the change is.
- **Never mark a draft pull request ready** (`gh pr ready`).
- Your work on a change **ends at the open PR with green checks**. Report the PR
  URL and stop. The ready-mark and the merge are the maintainer's sign-off.

## Worktree discipline

- Do implementation work in a dedicated Git worktree, not in the user's active
  checkout, unless the user explicitly asks otherwise.
- Name worktrees by task or branch, for example `../{{PROJECT_NAME}}-fix-timeout`.
- Before editing, inspect `git status -sb` in both the active checkout and the
  worktree you plan to use. Do not overwrite unrelated user changes.
- Keep each worktree scoped to one PR-sized change. If a task splits, create a
  second worktree/branch rather than mixing unrelated files.
- When a dependent PR has landed, fetch `origin main`, rebase the worktree branch
  onto it, resolve conflicts locally, rerun checks, and push with
  `--force-with-lease`.

## Workflows

- Pin every action to a full commit hash with its release as a comment
  (`uses: actions/checkout@<40-char sha> # v7.0.1`), never to a tag or branch. Pick a
  release at least 7 days old; Dependabot keeps pins current and waits the same 7 days
  (`cooldown` in `.github/dependabot.yml`).
- Give every `actions/checkout` `persist-credentials: false`, and each job only the
  `permissions:` it needs.
- `template-test` checks the first two in the template repository; Scorecard reports them
  in every repo.
- A job that branch protection requires is listed in `.github/required-checks.txt`. When
  you rename, add or drop one, change the file in the same PR and tell the maintainer to
  run `python3 -I scripts/repo-settings.py apply` after the merge; it needs admin rights.

## Publishing defaults

- Open draft PRs unless the user explicitly asks for ready-for-review.
- Every non-Dependabot PR must reference a real issue in the body. Use
  `Closes #N`, `Fixes #N`, or `Refs #N`; prefer closing keywords when the PR
  fully resolves the issue.
- Every commit must carry a DCO sign-off trailer. Use `git commit -s` for new
  commits. If a commit is missing the trailer, fix it before pushing with
  `git commit --amend -s --no-edit`.
- Verify sign-off before final push with `git log -1 --format=full`.
- After a rebase or amend on a published branch, push with
  `git push --force-with-lease`.

## Change discipline

- Every change starts from an issue, and the PR body links it (`Closes #NNN`, or
  `Refs #NNN` for partial work); the `require-linked-issue` check enforces it.
- One logical change per issue / branch / PR; split unrelated changes.
- Commits are signed off (`git commit -s`, [DCO](DCO)) with a
  conventional-prefix subject (`fix:`, `feat:`, `docs:`, `ci:`, `chore:`) and a
  body that explains the why.
- You must be able to explain every line you change. The person who opens the PR
  answers for it in review.
- Keep the checks green (the command is in [CONTRIBUTING.md](CONTRIBUTING.md)).

## Design documents — pick the right class, change it the right way

- **Pick the class by intent** (`docs/design/README.md` is the map):
  - **ADR** (`docs/design/adr/`) — a settled decision and its reasons (ADR-0001).
  - **Proposal** (`docs/design/proposals/`) — an implementation plan or milestone scope;
    ratified draft → accepted (ADR-0003).
  - **Spec** (`docs/design/specs/`) — a normative, versioned compatibility contract
    (bytes, wire format, conformance) (ADR-0003).
  - **Architecture overview** (`docs/design/architecture/`) — the living description of
    the current system; update it in the same PR whenever the system changes.
  - **Review** (`docs/design/reviews/`) — a dated go/no-go or readiness assessment.
- **Start from the template** in `docs/design/templates/` and add a row to the class index.
  For an ADR, follow [How an ADR is made](docs/design/adr/README.md#how-an-adr-is-made).
- **Never accept a design document.** Write ADRs as `Proposed` and proposals and specs as
  `draft`; changing the status to Accepted, accepted or stable is the maintainer's act
  after the architecture board agrees, like the merge.
- **Keep relative links working.** `docs-check` fails a PR with a Markdown link to a file or
  directory that isn't in the repo; run `python3 -I .github/docs-check/docs_links.py` before
  pushing a rename.
- **Changing a ratified doc = supersede, never rewrite.** Once an ADR is Accepted, a
  proposal accepted or a spec stable, its file is frozen (`docs-immutability` enforces
  this). To change it, write a **new** doc carrying `supersedes: <old>`, change only the old
  file's `status:` to superseded (optionally adding `superseded-by:`) and nothing else, and
  mark it superseded in the class index (ADR-0004). Small implementation facts go in the
  living architecture or code comments, not back into an accepted proposal.
- **Security-relevant changes** update the threat model (`docs/design/architecture/14-threat-model.md`
  and the summary in `.oss-scanner/threat_model.md`) in the same PR.
- **Leave the `How to fill this in` blocks to the maintainer** unless the task is to fill
  that document in.
