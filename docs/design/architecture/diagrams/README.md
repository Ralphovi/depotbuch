# Diagrams

Diagram source for the architecture overview: Mermaid (`.mermaid`) or D2 (`.d2`), never
binary image exports, so every change shows up in a diff and is reviewed in its PR.

Name files after what they show, for example `c4-context.mermaid`, `c4-container.mermaid`,
`write-path-sequence.mermaid`, and reference them from the section that explains them.
Example: wyrd's
[diagrams](https://github.com/getwyrd/wyrd/tree/main/docs/design/architecture/diagrams).

| File | Shows | Used in |
|------|-------|---------|
| [`c4-context.mermaid`](c4-context.mermaid) | depotbuch, its user and every external system | [§3](../03-context-and-scope.md) |

Smaller diagrams (containers, the domain model, sequences) are inline in the section that
explains them, so they render on GitHub next to their text.
