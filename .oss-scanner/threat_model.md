# Threat model: {{PROJECT_NAME}}

Reviewer-facing summary of what an attacker can reach and how bad each outcome is, for
security reviewers and scanners. The full, living threat model is
[architecture §14](../docs/design/architecture/14-threat-model.md). Where this file and §14
differ about what exists in code today, this file describes the code and §14 describes the
design it is growing into. A change that adds an untrusted input or moves a trust boundary
updates both in the same PR.

_Fill in each section; delete the italic prompts. Models:
[wyrd](https://github.com/getwyrd/wyrd/blob/main/.oss-scanner/threat_model.md),
[nl-shell](https://github.com/getwyrd/nl-shell/blob/main/.oss-scanner/threat_model.md)._

## What this project does

_The components and how data flows between them, in a few paragraphs or a small diagram._

## Where untrusted input enters

Treat all of the following as attacker-controlled:

1. _Each input an attacker can control: where it enters, who controls it, which component
   parses it._

Trusted: _what is not attacker-controlled, and why._

Already in place from the template: `.github/workflows/welcome-first-time-contributor.yml`
runs on `pull_request_target`, so it holds a token with `pull-requests: write` (its only
permission) while handling a pull request from any fork. The PR's code, title, body and
branch name are attacker-controlled. The workflow never checks the PR out and never
interpolates the event payload into its script; it reads only the author's login and the
PR number from the payload and posts a fixed comment. A change that adds an
`actions/checkout` step or a `${{ github.event` expression to that workflow is in scope.

## What must hold

- _The properties a finding breaks. These are what the security review checks._

## Components that matter most

In order: _the components, most exposed first._

Lower priority: _test tools, build automation._

Out of scope: _generated code; third-party code (report a dependency bug only if this
project's use of it is what makes it exploitable)._

## Known gaps: do not report these on their own

- _Each known, accepted gap, and what about it is still in scope._

## How to exercise it

_The test command, how to run the system locally, and how to drive the exposed inputs._

## How we rate severity

- **Critical:** _…_
- **High:** _…_
- **Medium:** _…_
- **Low:** _…_

A clean reproducer matters more than a severity label. The best form is a failing test in
the style of the existing ones.
