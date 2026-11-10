---
created: {{DATE}}
type: architecture
status: living
tags:
  - architecture
---
# 6. Runtime view

> Living document. How the components work together on the important paths. Open questions are marked **[OPEN]** inline.

> **How to fill this in:** The important paths through the system at run time, one
> subsection each: the main path first, then failure, repair and edge paths. Sequence
> diagrams go in `diagrams/`. Describe what happens and in what order; why it was designed
> that way belongs in ADRs. Replace each italic prompt with prose and delete this block once
> the section describes the real system. Example:
> [wyrd](https://github.com/getwyrd/wyrd/blob/main/docs/design/architecture/06-runtime-view.md).

## 6.1 The main path

_A Mermaid sequence diagram of the most common operation._

## 6.2 Other important paths

_Error handling, privileged operations, anything the threat model (§14) cares about._
