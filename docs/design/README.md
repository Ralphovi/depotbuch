---
created: {{DATE}}
type: index
tags:
  - index
---
# {{PROJECT_NAME}} — design documentation

The design documentation is organized into four classes, each with its own purpose,
audience and change process. Some documents describe the system and change with it, some
record decisions and never change, and some are contracts other code must honour. The
layout follows [wyrd](https://github.com/getwyrd/wyrd/tree/main/docs/design), which is the
reference project for it.

## The four document classes

| Class | Location | Nature | Change process |
|-------|----------|--------|----------------|
| 1. Specifications | `specs/` | Normative, versioned | Strict; a stable version is never edited, only replaced (ADR-0003) |
| 2. Architecture overview | `architecture/` | Descriptive, living | Edited continuously; always describes the current system |
| 3. Decision records (ADRs) | `adr/` | Immutable history | Append-only; superseded, never edited (ADR-0001) |
| 4. Enhancement proposals | `proposals/` | The change process | Draft → accepted → implemented; accepted records are immutable (ADR-0003) |

Alongside them, `reviews/` holds dated assessments (go/no-go calls, readiness and
consistency reviews) that are not one of the four classes. See
[`reviews/README.md`](reviews/README.md).

### 1. Specifications (`specs/`)

Contracts that more than one implementation, component or version depends on: a file
format, a wire format, a log or data schema. Written in RFC 2119 language (MUST / SHOULD /
MAY), with conformance vectors where the contract covers bytes or behavior. Most projects
start with none; write one before a second consumer depends on a format.

### 2. Architecture overview (`architecture/`)

A trimmed [arc42](https://arc42.org/) structure (a standard set of chapters for describing a
software architecture) plus [C4](https://c4model.com/) diagrams. It describes the system as
it currently is and must not lag the code: "update the architecture doc" is a legitimate
merge requirement on a PR that changes structure. Before there is code, it describes the
design the code is being built to.

### 3. Architecture Decision Records (`adr/`)

Short, numbered records of *why* a decision was made, so the same debate is not reopened in
every issue. An ADR is never edited after acceptance; a later ADR supersedes it (ADR-0004).
Format: a lightweight [Nygard-style](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
template.

### 4. Enhancement proposals (`proposals/`)

How larger changes and milestone plans are proposed, modeled on Kubernetes KEPs and Rust
RFCs. A proposal moves from `draft/` to `accepted/` and carries motivation, design,
alternatives and graduation criteria. The first one is usually the implementation arc: the
milestones in build order.

The fill-in templates for all four classes are in [`templates/`](templates/README.md).
**Which class?** A settled decision → ADR. A plan for work → proposal. A contract other code
must honour → spec. A description of how the system works now → architecture.

## Conventions

- **Diagrams as code.** Diagrams live in `architecture/diagrams/` as Mermaid or D2 source,
  never as binary exports, so they can be diffed and changed in a PR.
- **Docs live with code.** Documentation is in the same repository as the code it describes
  and is reviewed in the same pull requests.
- **ADR-first habit.** When a design question is settled, the output is an ADR, not an issue
  comment.
- **Frontmatter on every document.** `created`, `type` and `tags`; ratified classes also
  carry `status`, which the `docs-immutability` check reads.
- **Threat model.** The living model is [architecture §14](architecture/14-threat-model.md);
  [`.oss-scanner/threat_model.md`](../../.oss-scanner/threat_model.md) is a short summary for
  security reviewers and scanners that points at it.

## Reading order for newcomers

<!-- Adjust this list once the documents exist; wyrd's is in its design/README.md. -->

1. [`architecture/01-introduction-and-goals.md`](architecture/01-introduction-and-goals.md) — what this is and why.
2. [`architecture/05-building-block-view.md`](architecture/05-building-block-view.md) — the components.
3. [`adr/`](adr/README.md) — skim the index; the early ADRs are the fastest way to the *why*.
4. [`architecture/09-build-order-and-roadmap.md`](architecture/09-build-order-and-roadmap.md) — where to start contributing.
