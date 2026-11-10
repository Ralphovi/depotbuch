---
created: {{DATE}}
type: index
tags:
  - review
---
# Reviews

Dated assessments that inform a decision but are not one: go/no-go calls before a
milestone, readiness reviews, consistency or audit runs, and comparisons of options. A review
records what was checked, the evidence, and the verdict at that time. It is not edited
later; a newer review replaces it.

If a review settles a design question, the outcome goes into an ADR or proposal that cites
the review. The review itself stays as evidence.

**Naming:** `<topic>.md`, or `<milestone>-<topic>.md` for milestone gates. Frontmatter:
`created`, `type: review`, `author`, `tags`. Examples: wyrd's
[go/no-go review](https://github.com/getwyrd/wyrd/blob/main/docs/design/reviews/m4-fdb-go-no-go.md)
and [readiness review](https://github.com/getwyrd/wyrd/blob/main/docs/design/reviews/m4-observability-readiness.md).

## Index

| Review | Date | Verdict |
|--------|------|---------|
