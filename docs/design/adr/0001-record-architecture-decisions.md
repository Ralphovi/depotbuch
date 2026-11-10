---
created: {{DATE}}
type: adr
status: Accepted
tags:
  - adr
  - process
  - meta
---
# 0001. Record architecture decisions

## Context

{{PROJECT_NAME}} makes decisions early that later work depends on. Without a durable record,
the same questions come back in every issue and pull request, and the reasons are lost when
the code changes.

The living architecture overview (a trimmed arc42) describes the system as it is. It does
not record *why* it is that way, and it has a pull toward sections filled in only because
the template has them.

## Decision

We record architecture decisions as ADRs: short, numbered, append-only Markdown files in
`docs/design/adr/`, one decision per file, following the Nygard template (Context, Decision,
Consequences), with `created` / `type` / `status` / `tags` in YAML frontmatter. When a design
question is settled, in discussion, in review or anywhere else, the output is an ADR, not an
issue comment or a chat message.

This is the meta-decision, and the process below governs the **ADR class only**. Proposals
and specifications follow ADR-0003; the living architecture overview in
`../architecture/` is descriptive and not part of any acceptance flow.

### Numbering and location

ADRs are named `NNNN-kebab-title.md`, where `NNNN` is the next free zero-padded number.
Numbers are assigned monotonically and **never reused**. Every ADR is listed with its
current status in `docs/design/adr/README.md`.

### Lifecycle

The `status:` frontmatter field is the source of truth:

- **Proposed**: written up, not yet ratified. It may be edited freely while discussion
  continues, normally in the pull request that introduces it.
- **Accepted**: ratified by a deliberate edit to `status:` once the people named in
  `docs/governance/GOVERNANCE.md` agree the decision in review. This transition is the act
  of acceptance, not an automatic consequence of merging. From here the file is frozen.
- **Superseded**: a later ADR replaced the decision (ADR-0004 says how this is recorded).

An ADR is accepted only when it carries no unresolved **[OPEN]** items.

### Immutability

An Accepted ADR is never rewritten; that is what makes "see ADR-NNNN" a reference people can
trust. To change a decision, write a new ADR that names the one it replaces. The
`docs-immutability` check (`.github/workflows/docs-immutability.yml`) enforces this: it reads
each ADR's `status:` from the pull request's base, so a Proposed ADR may still be edited and
the Proposed → Accepted transition is allowed, but an Accepted ADR may not be modified,
deleted or renamed.

### Scope of arc42

The architecture overview deliberately uses about ten of arc42's twelve sections. Nobody
should "helpfully" complete the rest.

### Starting a new ADR

Copy `../templates/adr.md`, give it the next free number, fill in Context / Decision /
Consequences, open it as **Proposed**, and add a row to the index.

## Consequences

- Newcomers can read the ADRs to learn the *why* of the system quickly.
- Settled debates are not reopened; objections are met with "see ADR-NNNN".
- Decisions must be written up, which is a small, intended cost.
- The ADRs are append-only history, distinct from the living overview in
  `docs/design/architecture/`.
