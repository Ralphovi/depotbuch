# {{PROJECT_NAME}} — documentation

> {{PROJECT_DESCRIPTION}}

This folder is the single source of truth for {{PROJECT_NAME}}'s documentation. It is
plain Markdown, editable in any editor or in Obsidian, and reviewed in the same pull
requests as the code.

## Where things live

| Path | What it is |
|------|------------|
| [`design/`](design/README.md) | **Start here.** Architecture, specifications, decision records and proposals, in four classes with different change processes. |
| [`design/templates/`](design/templates/README.md) | Fill-in templates for each class. Copy, don't edit in place. |
| [`design/reviews/`](design/reviews/README.md) | Dated go/no-go and readiness reviews. |
| [`governance/`](governance/GOVERNANCE.md) | Who decides what, how people gain and lose roles, and the [Code of Conduct](governance/CODE_OF_CONDUCT.md). |
| [`NAME.md`](NAME.md) | Why the project is called {{PROJECT_NAME}}. |
| [`../.oss-scanner/threat_model.md`](../.oss-scanner/threat_model.md) | Short threat-model summary for security reviewers; the full model is architecture §14. |

<!-- Add rows here for anything else the project keeps under docs/, for example a
     publishing/ folder if the docs are rendered to a website, as wyrd does. -->

New here? Read the [design documentation overview](design/README.md) for how the docs are
organized and the reading order.
