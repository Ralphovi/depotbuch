# {{PROJECT_NAME}}

{{PROJECT_DESCRIPTION}}

<!-- template:begin -->
> **This is a GitHub template repository.** It holds the setup shared by eduralph, Ralphovi
> and getwyrd projects, with [wyrd](https://github.com/getwyrd/wyrd) as the reference:
>
> - the design-documentation layout: four document classes under `docs/design/`,
>   governance under `docs/governance/`, and the `docs-immutability` check;
> - the PR rules: DCO sign-off (`dco`) and a linked issue on every PR
>   (`require-linked-issue`), plus a contributing guide that points at the
>   [shared one](https://github.com/eduralph/.github/blob/main/CONTRIBUTING.md), and a
>   welcome comment on a contributor's first PR;
> - issue handling: bug and enhancement templates, the `new` label kept in step with the
>   milestone, and automated priority triage (ADR-0005) that stays off until it is set up;
> - SECURITY.md, Dependabot, the agent rules in AGENTS.md and Claude Code permissions;
> - hardened workflows: every action pinned to a commit hash, no credentials left after
>   checkout, CodeQL code scanning, and a weekly OpenSSF Scorecard run.
>
> Each file still to be written carries a **How to fill this in** block. For projects
> driven by the PDCA quality cycle, use
> [pdca-project-template](https://github.com/eduralph/pdca-project-template) instead.
>
> ### Start a new project
>
> ```bash
> gh repo create <owner>/<name> --public --template eduralph/project-template \
>   --description "<one line>" --clone
> cd <name>
> scripts/init-repo.sh          # asks three questions, fills placeholders, applies settings
> ```
>
> `init-repo.sh` asks for the license (Apache-2.0 by default), the contact address for
> conduct and policy reports, and the package ecosystem for Dependabot. It replaces the
> `{{…}}` placeholders and commits and pushes that once to `main`, removing itself and this
> block. For `cargo` it also pins the RustSec advisory database the gate audits
> (`scripts/advisory-db.sh`, `deny.toml`): Dependabot moves the pin daily, and a daily
> workflow checks `main` against the newest database and opens an issue for a new advisory.
> It then creates the labels and runs `scripts/repo-settings.py apply`, which deletes
> branches after merge, turns on the security settings (vulnerability reporting, Dependabot
> security updates, secret scanning with push protection and generic-secret patterns,
> CodeQL code scanning, a read-only Actions token, the immutable OIDC subject), and
> protects `main` (PRs required; the checks in `.github/required-checks.txt` required;
> admins included). GitHub doesn't copy labels, settings or protection rules from a
> template, which is why the script exists. At the end it prints what is left to do by
> hand.
>
> `repo-settings.py` stays in the new repo. `python3 -I scripts/repo-settings.py check`
> reads the settings back at any time and lists any that have changed; `apply` sets them
> again.
>
> Changes to the template itself are tested by `template-test`, which runs `init-repo.sh`
> and `repo-settings.py` against a fake GitHub (`.github/template-test/`). It runs only in
> the template repo.
<!-- template:end -->

## Status

Early.

## Documentation

[`docs/`](docs/README.md) is the map. Design documents are in [`docs/design/`](docs/design/README.md):
architecture, decision records (ADRs), proposals and specifications. Governance and the Code
of Conduct are in [`docs/governance/`](docs/governance/GOVERNANCE.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and, for coding agents, [AGENTS.md](AGENTS.md).

## License

Copyright © {{YEAR}} {{AUTHOR}}.

{{PROJECT_NAME}} is licensed under the **{{LICENSE_NAME}}** ([LICENSE](LICENSE)).

Contributions are accepted under the same license and gated on the
[Developer Certificate of Origin](DCO). Sign off commits with `git commit -s`.
