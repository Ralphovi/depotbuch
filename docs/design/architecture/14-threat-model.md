---
created: 10.11.2026 19:03
type: architecture
status: living
tags:
  - architecture
  - security
  - threat-model
---
# 14. Threat model

> Living document. What is worth attacking, where the trust boundaries are, who the
> adversaries are, and which attacks depotbuch must withstand, each mapped to what
> mitigates it and the test that checks it. Open questions are marked **[OPEN]** inline.

> **How to fill this in:** start small and grow it as surfaces are built; a threat model is
> never complete. Fill §14.1–§14.3 first, before code exists. Add §14.4–§14.7 as each trust
> boundary appears in code. A change that adds an untrusted input or moves a trust boundary
> updates this section in the same PR, and the short summary in
> `.oss-scanner/threat_model.md` with it. Replace each italic prompt and delete this block
> once the first three subsections are written. Example:
> [wyrd](https://github.com/getwyrd/wyrd/blob/main/docs/design/architecture/14-threat-model.md).

## 14.1 Assets

_What is worth protecting: data, keys, availability, integrity of results. For each, what
losing it means for users._

## 14.2 Trust boundaries

_Where data or control crosses from less trusted to more trusted: network inputs, files from
users, plugins, other services. A diagram in `diagrams/` helps._

- **Pull requests from forks, in GitHub Actions.** A PR's code, title, body and branch name
  are attacker-controlled: anyone can open one. The checks run on `pull_request`, where the
  token is read-only and `actions/checkout` keeps no credentials, so PR-supplied code runs
  without write access. One workflow, `welcome-first-time-contributor.yml`, runs on
  `pull_request_target` instead, because a fork PR's `pull_request` token cannot comment;
  it holds `pull-requests: write` (its only permission) while handling a PR from anyone.
  That boundary holds only while the workflow neither checks the PR out nor interpolates
  the event payload into its script. It reads the author's login and the PR number through
  `context.payload` at run time and posts a fixed comment. The template checks both rules
  before the workflow ships (`test_pull_request_target_never_touches_pr_content` in its
  `template-test`): no `actions/checkout` step and no `${{ github.event` expression in a
  `pull_request_target` workflow. That test is not copied into this project, so a change
  to the workflow is reviewed by hand against the same two rules.

## 14.3 Adversaries

_Who might attack and what they can already do: an anonymous network user, an authenticated
user, a compromised dependency, an operator with too much access._

## 14.4 STRIDE, per boundary

_For each boundary in §14.2: spoofing, tampering, repudiation, information disclosure,
denial of service, elevation of privilege. Only the ones that apply._

## 14.5 Attack catalog

_The concrete attacks this kind of system must withstand, each with the decision (ADR) or
mechanism that mitigates it._

## 14.6 Abuse-case tests

_Tests that play the attacker: malformed input, replay, resource exhaustion, privilege
probing._

## 14.7 Threat → test map

_A table: threat, mitigation, the test that proves it. A threat without a test is a gap
(§14.9)._

## 14.8 Residual and accepted risks

_What is not mitigated, why that is acceptable, and who accepted it._

## 14.9 Gaps and their disposition

_Known gaps, each with an issue or milestone that closes it._
