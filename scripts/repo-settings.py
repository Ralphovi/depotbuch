#!/usr/bin/env python3
"""Apply or check a repo's GitHub settings. Stdlib only; needs gh, logged in as an admin.

    python3 -I scripts/repo-settings.py check [owner/repo]
    python3 -I scripts/repo-settings.py apply [owner/repo]

`check` changes nothing: it reads every setting below, prints the ones that differ and
exits 1 if any do. `apply` changes only what differs, then checks again. Both work from
the same list, so a clean `check` means `apply` would change nothing. Without owner/repo
they use the repo of the current checkout.

The settings:
- the wiki is off, and a pull request's branch is deleted when it merges;
- private vulnerability reporting, Dependabot alerts and Dependabot security updates on;
- secret scanning with push protection and generic-secret patterns on;
- code scanning with GitHub's CodeQL default setup;
- the Actions token is read-only and can't approve pull requests;
- the OIDC subject (what a workflow's identity token says about the repo) uses the
  repo's and owner's immutable IDs, so a renamed repo can't inherit a federation rule;
- the default branch is protected: pull requests required (no approvals, since most
  projects have one maintainer), the status checks in .github/required-checks.txt
  required, admins included, conversations resolved, no force-push or deletion.

The required checks come from .github/required-checks.txt on the repo's default branch
(one per line; `#` starts a comment), or from --checks-file for a repo that doesn't
carry the file yet. Each is the name of a job in .github/workflows/.

Three settings depend on what GitHub offers the repo:
- generic-secret scanning is only reported for repos on a personal account, where GitHub
  accepts the request but leaves it off;
- a private repo skips private vulnerability reporting (public repos only) and CodeQL
  (private repos need paid Code Security; it is checked if GitHub has it on);
- a repo with a Claude Console federation rule (variable ANTHROPIC_FEDERATION_RULE_ID)
  keeps its OIDC subject unless --change-oidc-subject is given, because the rule matches
  the old subject and issue triage would stop working. Point the rule at the new subject
  (`repo:<owner>@<id>/<repo>@<id>:ref:refs/heads/main`) first.

Exit status: 0 = matches, 1 = differs (after apply: still differs), 2 = gh or usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

CHECKS_FILE = ".github/required-checks.txt"
FEDERATION_VARIABLE = "ANTHROPIC_FEDERATION_RULE_ID"
# A write takes a few seconds to show in GitHub's reads, so apply reads again this many
# times, this many seconds apart, before it reports a setting it just set as different.
READS_AFTER_APPLY = 5
READ_DELAY = float(os.environ.get("REPO_SETTINGS_READ_DELAY", "3"))


class GhError(Exception):
    pass


def gh(*args: str, stdin: str | None = None) -> str:
    result = subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True)
    if result.returncode != 0:
        raise GhError(f"gh {' '.join(args)}: {result.stderr.strip() or 'failed'}")
    return result.stdout


def get(path: str) -> dict | None:
    """The JSON at an API path: {} for an empty answer, None when GitHub refuses (404, 403)."""
    try:
        out = gh("api", path)
    except GhError:
        return None
    return json.loads(out) if out.strip() else {}


def parse_checks(text: str) -> list[str]:
    names = [line.split("#", 1)[0].strip() for line in text.splitlines()]
    return [n for n in names if n]


def read(repo: str) -> dict:
    base = f"repos/{repo}"
    meta = get(base)
    if meta is None:
        raise GhError(f"can't read {repo}; check the name and `gh auth status`")
    branch = meta["default_branch"]
    return {
        "repo": meta,
        "branch": branch,
        "pvr": get(f"{base}/private-vulnerability-reporting"),
        "alerts": get(f"{base}/vulnerability-alerts"),
        "fixes": get(f"{base}/automated-security-fixes"),
        "codeql": get(f"{base}/code-scanning/default-setup"),
        "token": get(f"{base}/actions/permissions/workflow"),
        "oidc": get(f"{base}/actions/oidc/customization/sub"),
        "protection": get(f"{base}/branches/{branch}/protection"),
        "federation": get(f"{base}/actions/variables/{FEDERATION_VARIABLE}") is not None,
    }


def rows(state: dict, checks: list[str]) -> list[tuple[str, object, object, str]]:
    """(setting, actual, wanted, fix) for each setting. `fix` names the write in FIXES that
    sets it, or starts with `note:` / `skip:` for a setting that is reported, not changed."""
    meta = state["repo"]
    private = meta["visibility"] != "public"
    personal = meta["owner"]["type"] != "Organization"
    security = meta.get("security_and_analysis") or {}

    def status(key: str) -> str:
        return (security.get(key) or {}).get("status", "unavailable")

    out: list[tuple[str, object, object, str]] = [
        ("wiki", meta["has_wiki"], False, "repo"),
        ("delete branch on merge", meta["delete_branch_on_merge"], True, "repo"),
    ]
    if private:
        out.append(("private vulnerability reporting", None, None, "skip: public repos only"))
    else:
        out.append(("private vulnerability reporting",
                    (state["pvr"] or {}).get("enabled", False), True, "pvr"))
    out += [
        ("Dependabot alerts", state["alerts"] is not None, True, "alerts"),
        ("Dependabot security updates", (state["fixes"] or {}).get("enabled", False), True,
         "fixes"),
        ("secret scanning", status("secret_scanning"), "enabled", "secrets"),
        ("secret scanning push protection", status("secret_scanning_push_protection"),
         "enabled", "secrets"),
        ("generic-secret scanning", status("secret_scanning_non_provider_patterns"), "enabled",
         "note: GitHub leaves it off for repos on a personal account" if personal
         else "secrets"),
    ]
    if private and state["codeql"] is None:
        out.append(("code scanning (CodeQL)", None, None,
                    "skip: private repos need GitHub Code Security"))
    else:
        out.append(("code scanning (CodeQL)", (state["codeql"] or {}).get("state", "unavailable"),
                    "configured", "codeql"))
    token = state["token"] or {}
    oidc = state["oidc"] or {}
    out += [
        ("Actions token", token.get("default_workflow_permissions"), "read", "token"),
        ("Actions token approves PRs", token.get("can_approve_pull_request_reviews"), False,
         "token"),
        ("OIDC subject uses immutable IDs",
         bool(oidc.get("use_default")) and bool(oidc.get("use_immutable_subject")), True, "oidc"),
    ]

    branch = state["branch"]
    protection = state["protection"]
    if protection is None:
        return out + [(f"branch protection on {branch}", "off", "on", "protection")]

    def enabled(key: str) -> bool | None:
        return (protection.get(key) or {}).get("enabled")

    status_checks = protection.get("required_status_checks") or {}
    reviews = protection.get("required_pull_request_reviews")
    return out + [
        (f"{branch}: required checks", sorted(status_checks.get("contexts") or []),
         sorted(checks), "protection"),
        (f"{branch}: checks must be up to date with {branch}", status_checks.get("strict", False),
         False, "protection"),
        (f"{branch}: pull requests required (approvals)",
         reviews.get("required_approving_review_count") if reviews else "not required", 0,
         "protection"),
        (f"{branch}: rules apply to admins", enabled("enforce_admins"), True, "protection"),
        (f"{branch}: conversations resolved", enabled("required_conversation_resolution"), True,
         "protection"),
        (f"{branch}: force-push allowed", enabled("allow_force_pushes"), False, "protection"),
        (f"{branch}: deletion allowed", enabled("allow_deletions"), False, "protection"),
    ]


def to_fix(state: dict, checks: list[str]) -> list[str]:
    """The writes in FIXES that would bring the differing settings in line, in order."""
    todo: list[str] = []
    for _, actual, wanted, how in rows(state, checks):
        if actual != wanted and ":" not in how and how not in todo:
            todo.append(how)
    return todo


def fmt(value: object) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, list):
        return ", ".join(value) or "none"
    return "unset" if value is None else str(value)


def fix(name: str, repo: str, branch: str, checks: list[str]) -> None:
    base = f"repos/{repo}"
    if name == "repo":
        gh("api", "-X", "PATCH", base, "-F", "has_wiki=false", "-F", "delete_branch_on_merge=true")
    elif name == "pvr":
        gh("api", "-X", "PUT", f"{base}/private-vulnerability-reporting")
    elif name == "alerts":
        gh("api", "-X", "PUT", f"{base}/vulnerability-alerts")
    elif name == "fixes":
        gh("api", "-X", "PUT", f"{base}/automated-security-fixes")
    elif name == "secrets":
        on = {"status": "enabled"}
        gh("api", "-X", "PATCH", base, "--input", "-", stdin=json.dumps({"security_and_analysis": {
            "secret_scanning": on, "secret_scanning_push_protection": on,
            "secret_scanning_non_provider_patterns": on}}))
    elif name == "codeql":
        # Setup carries on in the background; the check afterwards reports what GitHub says.
        gh("api", "-X", "PATCH", f"{base}/code-scanning/default-setup", "-f", "state=configured")
    elif name == "token":
        gh("api", "-X", "PUT", f"{base}/actions/permissions/workflow",
           "-f", "default_workflow_permissions=read", "-F", "can_approve_pull_request_reviews=false")
    elif name == "oidc":
        gh("api", "-X", "PUT", f"{base}/actions/oidc/customization/sub",
           "-F", "use_default=true", "-F", "use_immutable_subject=true")
    elif name == "protection":
        gh("api", "-X", "PUT", f"{base}/branches/{branch}/protection", "--input", "-",
           stdin=json.dumps({
               "required_status_checks": {"strict": False, "contexts": checks},
               "enforce_admins": True,
               "required_pull_request_reviews": {"required_approving_review_count": 0},
               "restrictions": None,
               "required_conversation_resolution": True,
               "allow_force_pushes": False,
               "allow_deletions": False,
           }))
    else:
        raise ValueError(name)


def report(repo: str, state: dict, checks: list[str], source: str) -> int:
    meta = state["repo"]
    print(f"{repo} ({meta['visibility']}, {meta['owner']['type'].lower()} account); "
          f"required checks from {source}")
    differ = 0
    for setting, actual, wanted, how in rows(state, checks):
        if how.startswith("skip:"):
            print(f"  skip  {setting}: {how[5:].strip()}")
        elif actual == wanted:
            print(f"  ok    {setting}: {fmt(actual)}")
        elif how.startswith("note:"):
            print(f"  note  {setting}: {fmt(actual)} ({how[5:].strip()})")
        else:
            differ += 1
            print(f"  DIFF  {setting}: {fmt(actual)}, want {fmt(wanted)}")
    print(f"repo-settings: {differ} setting{'s' if differ != 1 else ''} differ"
          f"{'s' if differ == 1 else ''}")
    return 1 if differ else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply or check a repo's GitHub settings.")
    parser.add_argument("mode", choices=["check", "apply"])
    parser.add_argument("repo", nargs="?", help="owner/repo (default: this checkout's repo)")
    parser.add_argument("--checks-file", help=f"required checks to use instead of {CHECKS_FILE}")
    parser.add_argument("--change-oidc-subject", action="store_true",
                        help="change the OIDC subject even though a federation rule uses it")
    args = parser.parse_args()

    try:
        repo = args.repo or gh("repo", "view", "--json", "nameWithOwner",
                               "--jq", ".nameWithOwner").strip()
        state = read(repo)
        if args.checks_file:
            with open(args.checks_file, encoding="utf-8") as fh:
                checks, source = parse_checks(fh.read()), args.checks_file
        else:
            try:
                text = gh("api", f"repos/{repo}/contents/{CHECKS_FILE}?ref={state['branch']}",
                          "-H", "Accept: application/vnd.github.raw")
            except GhError:
                print(f"repo-settings: {repo} has no {CHECKS_FILE} on {state['branch']}; "
                      "add it or pass --checks-file", file=sys.stderr)
                return 2
            checks, source = parse_checks(text), CHECKS_FILE
        if not checks:
            print(f"repo-settings: no required checks in {source}", file=sys.stderr)
            return 2

        if args.mode == "apply":
            todo = to_fix(state, checks)
            for name in todo:
                if name == "oidc" and state["federation"] and not args.change_oidc_subject:
                    print(f"repo-settings: left the OIDC subject alone: {FEDERATION_VARIABLE} "
                          "is set, so a federation rule matches the current subject. Point "
                          "the rule at the new subject, then re-run with --change-oidc-subject.")
                    continue
                try:
                    fix(name, repo, state["branch"], checks)
                    print(f"repo-settings: set {name}")
                except GhError as exc:
                    print(f"repo-settings: {exc}")
            for attempt in range(READS_AFTER_APPLY if todo else 1):
                if attempt:
                    time.sleep(READ_DELAY)
                state = read(repo)
                if not to_fix(state, checks):
                    break
        return report(repo, state, checks, source)
    except (GhError, OSError) as exc:
        print(f"repo-settings: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
