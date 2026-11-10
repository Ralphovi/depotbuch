---
created: {{DATE}}
type: index
tags:
  - spec
---
# Specifications

Normative, versioned contracts (ADR-0003). This index is the authoritative record of each
spec version's status and supersession (ADR-0004).

**When to write one:** before a second consumer depends on a format, such as a file layout,
a wire protocol, or a log or data schema that one component writes and another reads. Most
interfaces don't need a spec; a versioned schema in code is enough. Write a spec when the
contract must outlive the implementation (data written today must be readable years later)
or when someone else may implement it.

**Layout:** `<domain>/v<N>.md` from `../templates/spec.md`. Conformance vectors for a version
go in `conformance/vectors/v<N>/` (valid inputs) and `conformance/invalid/v<N>/` (inputs a
reader must reject); for a stable version they are frozen with the spec. Example: wyrd's
[chunk-format spec](https://github.com/getwyrd/wyrd/tree/main/docs/design/specs/chunk-format)
and its [conformance vectors](https://github.com/getwyrd/wyrd/tree/main/docs/design/specs/conformance).

## Index

| Spec | Version | Status |
|------|---------|--------|
