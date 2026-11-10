"""Run scripts/init-repo.sh the way a new project would, against a stub gh.

    python3 -I -m unittest discover -s .github/template-test -v

Each case copies the tracked files of this checkout (as they are on disk, so uncommitted
edits are tested too) into a throwaway repo with a local bare remote, runs init-repo.sh
non-interactively with a license and a Dependabot ecosystem, and checks the result: the
script succeeds, no placeholder is left, the template-only files are gone, LICENSE,
NOTICE and dependabot.yml match the answers, and the GitHub calls the script makes
(logged by stub/gh, which keeps the repo's settings like GitHub would) include every
expected setting. It also checks that each status check branch protection requires is
reported by a job in .github/workflows/, so a renamed job can't leave new repos waiting
forever on a check that never runs. test_repo_settings.py tests the settings script on
its own.

A second test checks the template's workflows themselves: every action is pinned to a
full commit hash with its release in a comment, and every actions/checkout sets
`persist-credentials: false`. That includes the Rust-only workflow staged in
.github/cargo/, which Dependabot does not read, so its pins must also match the ones in
.github/workflows/ that Dependabot keeps current. A `pull_request_target` workflow runs
with write access, so it must not check out the PR's code or interpolate the event.

For cargo, init-repo.sh pins the RustSec advisory database at the newest commit of its
main branch; ADVISORY_DB_URL points it at a local stand-in here.

The stub answers everything except license texts, which come from the real gh ($REAL_GH,
found on PATH), so the non-Apache cases need network access and a gh login or GH_TOKEN.
What this cannot test is whether GitHub accepts the calls; that takes one run on a
throwaway repo, after which `scripts/repo-settings.py check` shows what GitHub did.

init-repo.sh deletes this folder from repos created from the template.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(
    subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=HERE, check=True,
                   capture_output=True, text=True).stdout.strip()
)
REPO = "eduralph/demo"
PLACEHOLDER = re.compile(r"\{\{[A-Z_]+\}\}")
USES = re.compile(r"^(\s*)(?:#\s*)?-?\s*uses:\s*(\S+)(.*)$")
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")

# (license, Dependabot ecosystem): the default, a license fetched from GitHub with no
# extra ecosystem, and a copyleft license with another ecosystem.
CASES = [("apache-2.0", "pip"), ("mit", "none"), ("gpl-3.0", "cargo")]
LICENSE_MARKER = {
    "apache-2.0": "Apache License",
    "mit": "MIT License",
    "gpl-3.0": "GNU GENERAL PUBLIC LICENSE",
}

# Calls init-repo.sh must make, as the stub logs them (a prefix of the logged line).
EXPECTED_CALLS = [
    f"gh label create sev:critical --repo {REPO}",
    f"gh label create priority:P0 --repo {REPO}",
    f"gh label create needs-triage --repo {REPO}",
    f"gh label create new --repo {REPO}",
    f"gh label create release-gating --repo {REPO}",
    f"gh api -X PATCH repos/{REPO} -F has_wiki=false -F delete_branch_on_merge=true",
    f"gh api -X PUT repos/{REPO}/private-vulnerability-reporting",
    f"gh api -X PUT repos/{REPO}/vulnerability-alerts",
    f"gh api -X PUT repos/{REPO}/automated-security-fixes",
    f"gh api -X PATCH repos/{REPO} --input -",
    f"gh api -X PATCH repos/{REPO}/code-scanning/default-setup -f state=configured",
    f"gh api -X PUT repos/{REPO}/actions/permissions/workflow -f default_workflow_permissions=read",
    f"gh api -X PUT repos/{REPO}/actions/oidc/customization/sub -F use_default=true -F use_immutable_subject=true",
    f"gh api -X PUT repos/{REPO}/branches/main/protection --input -",
]
# Labels the example area must never become in a real repo.
FORBIDDEN_CALLS = [f"gh label create area:core --repo {REPO}"]
SECRET_SETTINGS = ["secret_scanning", "secret_scanning_push_protection",
                   "secret_scanning_non_provider_patterns"]
FRESH_STATE = HERE / "stub" / "fresh-repo.json"
CHECKS_FILE = ".github/required-checks.txt"
TEMPLATE_ONLY = ["scripts/init-repo.sh", ".github/template-test/test_init_repo.py",
                 ".github/template-test/stub/gh", ".github/workflows/template-test.yml"]


def git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True, env=env).stdout


def stdin_after(log: str, call: str) -> str:
    """The JSON the stub logged after `call` (a call that read `--input -`)."""
    lines = log.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(call))
    body = []
    for line in lines[start + 1:]:
        if line.startswith("gh "):
            break
        body.append(line)
    return "\n".join(body)


def workflow_files(root: Path) -> list[Path]:
    """The template's workflows, with the Rust-only one init-repo.sh moves in for cargo."""
    return sorted([*(root / ".github" / "workflows").glob("*.yml"),
                   *(root / ".github" / "cargo").glob("*.yml")])


def required_checks(root: Path) -> list[str]:
    lines = (root / CHECKS_FILE).read_text(encoding="utf-8").splitlines()
    return [n for n in (line.split("#", 1)[0].strip() for line in lines) if n]


def reported_checks(root: Path) -> set[str]:
    """The check names the workflows report: each job's `name:`, or its id without one."""
    names = set()
    for wf in sorted((root / ".github" / "workflows").glob("*.yml")):
        in_jobs, job, name = False, None, None
        for line in wf.read_text(encoding="utf-8").splitlines() + ["end:"]:
            if re.match(r"^\S", line):
                if job:
                    names.add(name or job)
                in_jobs, job, name = line.startswith("jobs:"), None, None
                continue
            m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
            if in_jobs and m:
                if job:
                    names.add(name or job)
                job, name = m[1], None
                continue
            m = re.match(r"^    name:\s*(.+?)\s*$", line)
            if in_jobs and job and m:
                name = m[1].strip("\"'")
    return names


class Workflows(unittest.TestCase):
    def test_required_checks_are_reported(self) -> None:
        missing = set(required_checks(ROOT)) - reported_checks(ROOT)
        self.assertEqual(missing, set(), f"{CHECKS_FILE} names checks no workflow job reports")

    def test_actions_pinned_and_credentials_not_persisted(self) -> None:
        problems = []
        for wf in workflow_files(ROOT):
            lines = wf.read_text(encoding="utf-8").splitlines()
            for n, line in enumerate(lines, 1):
                m = USES.match(line)
                if not m or m[2].startswith("./"):
                    continue
                where = f"{wf.name}:{n}"
                if not PINNED.match(m[2]) or not re.match(r"\s*#\s*v\d", m[3]):
                    problems.append(f"{where}: pin {m[2]} to a commit hash, "
                                    "with the release as a comment (`@<sha> # vX.Y.Z`)")
                if m[2].startswith("actions/checkout@") and not line.lstrip().startswith("#"):
                    indent = len(m[1]) + 2  # the step's keys sit under `- `
                    block = []
                    for later in lines[n:]:
                        if later.strip() and len(later) - len(later.lstrip()) < indent:
                            break
                        block.append(later.strip())
                    if "persist-credentials: false" not in block:
                        problems.append(f"{where}: actions/checkout without "
                                        "`persist-credentials: false`")
        self.assertEqual(problems, [])

    def test_pull_request_target_never_touches_pr_content(self) -> None:
        """That trigger runs with write access, so PR content must stay out of it."""
        for wf in workflow_files(ROOT):
            text = wf.read_text(encoding="utf-8")
            if re.search(r"^\s*pull_request_target:", text, re.M):
                with self.subTest(wf.name):
                    self.assertNotIn("actions/checkout", text)
                    self.assertNotIn("${{ github.event", text)

    def test_staged_workflows_use_the_dependabot_kept_pins(self) -> None:
        def pins(paths: list[Path]) -> dict[str, set[str]]:
            found: dict[str, set[str]] = {}
            for wf in paths:
                for line in wf.read_text(encoding="utf-8").splitlines():
                    m = USES.match(line)
                    if m and "@" in m[2] and not line.lstrip().startswith("#"):
                        action, ref = m[2].split("@", 1)
                        found.setdefault(action, set()).add(f"{ref}{m[3]}")
            return found

        kept = pins(sorted((ROOT / ".github" / "workflows").glob("*.yml")))
        staged = pins(sorted((ROOT / ".github" / "cargo").glob("*.yml")))
        for action, refs in staged.items():
            self.assertIn(action, kept, f".github/cargo uses {action}, which no workflow in "
                          ".github/workflows uses, so Dependabot would never update it")
            self.assertEqual(refs, kept[action], f"{action}: .github/cargo pins it differently "
                             "from .github/workflows")


class InitRepo(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        real_gh = shutil.which("gh")
        self.env = {
            **os.environ,
            "HOME": str(self.tmp),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Template Test",
            "GIT_AUTHOR_EMAIL": "template-test@example.invalid",
            "GIT_COMMITTER_NAME": "Template Test",
            "GIT_COMMITTER_EMAIL": "template-test@example.invalid",
            "PATH": f"{HERE / 'stub'}{os.pathsep}{os.environ['PATH']}",
            "REAL_GH": real_gh or "false",
            "PROJECT_CONTACT": "policy@example.org",
        }
        # A stand-in for the RustSec advisory database: one commit on main.
        advisory_db = self.tmp / "advisory-db.git"
        git(self.tmp, "init", "-q", "-b", "main", str(advisory_db))
        git(advisory_db, "commit", "-q", "--allow-empty", "-m", "advisories", env=self.env)
        self.advisory_pin = git(advisory_db, "rev-parse", "HEAD").strip()
        self.env["ADVISORY_DB_URL"] = str(advisory_db)
        # The real gh needs the user's config for its login when GH_TOKEN isn't set.
        if "GH_TOKEN" not in os.environ and "GITHUB_TOKEN" not in os.environ:
            self.env["GH_CONFIG_DIR"] = os.environ.get(
                "GH_CONFIG_DIR", str(Path.home() / ".config" / "gh"))

    def make_repo(self, name: str) -> Path:
        """A fresh repo holding this checkout's tracked files, pushed to a bare remote."""
        repo, remote = self.tmp / name, self.tmp / f"{name}.git"
        tracked = git(ROOT, "ls-files", "-z").split("\0")
        for path in filter(None, tracked):
            src = ROOT / path
            if not src.is_file():
                continue  # deleted in the working tree
            dest = repo / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        git(self.tmp, "init", "-q", "--bare", str(remote))
        git(repo.parent, "init", "-q", "-b", "main", str(repo))
        git(repo, "remote", "add", "origin", str(remote))
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "template", env=self.env)
        git(repo, "push", "-q", "origin", "main", env=self.env)
        return repo

    def run_init(self, repo: Path, license_id: str, ecosystem: str) -> str:
        log = self.tmp / f"{repo.name}.log"
        state = self.tmp / f"{repo.name}.json"
        shutil.copy(FRESH_STATE, state)
        env = {**self.env, "STUB_LOG": str(log), "STUB_STATE": str(state),
               "PROJECT_LICENSE": license_id, "PROJECT_ECOSYSTEM": ecosystem}
        result = subprocess.run(["bash", "scripts/init-repo.sh"], cwd=repo, env=env,
                                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                timeout=300)
        self.assertEqual(result.returncode, 0,
                         f"init-repo.sh failed:\n{result.stdout}\n{result.stderr}")
        return log.read_text(encoding="utf-8") if log.exists() else ""

    def test_init_repo(self) -> None:
        for license_id, ecosystem in CASES:
            with self.subTest(license=license_id, ecosystem=ecosystem):
                repo = self.make_repo(f"{license_id}-{ecosystem}")
                log = self.run_init(repo, license_id, ecosystem)
                self.check_tree(repo, license_id, ecosystem)
                self.check_calls(log, repo)

    def check_tree(self, repo: Path, license_id: str, ecosystem: str) -> None:
        self.assertEqual(git(repo, "status", "--porcelain"), "", "init-repo.sh left changes uncommitted")
        self.assertEqual(git(repo, "rev-parse", "HEAD"), git(repo, "rev-parse", "origin/main"),
                         "init-repo.sh did not push its commit")
        files = set(filter(None, git(repo, "ls-files", "-z").split("\0")))
        for path in TEMPLATE_ONLY:
            self.assertNotIn(path, files, f"{path} should be removed")
        left = [p for p in sorted(files) if (repo / p).is_file()
                and PLACEHOLDER.search((repo / p).read_text(encoding="utf-8", errors="replace"))]
        self.assertEqual(left, [], "placeholders left")
        self.assertNotIn("template:begin", (repo / "README.md").read_text(encoding="utf-8"))
        self.assertIn(LICENSE_MARKER[license_id], (repo / "LICENSE").read_text(encoding="utf-8"))
        self.assertEqual("NOTICE" in files, license_id == "apache-2.0", "NOTICE is for Apache-2.0 only")
        dependabot = (repo / ".github" / "dependabot.yml").read_text(encoding="utf-8")
        self.assertIn("package-ecosystem: github-actions", dependabot)
        if ecosystem != "none":
            self.assertIn(f"package-ecosystem: {ecosystem}", dependabot)
        cargo = ecosystem == "cargo"
        self.assertEqual(dependabot.count("package-ecosystem:"),
                         1 + (ecosystem != "none") + cargo)
        # Every entry but the advisory database's waits out the cooldown.
        self.assertEqual(dependabot.count("default-days: 7"),
                         dependabot.count("package-ecosystem:") - cargo)
        self.check_advisory_pin(repo, files, dependabot, cargo)

    def check_advisory_pin(self, repo: Path, files: set[str], dependabot: str,
                           cargo: bool) -> None:
        self.assertFalse(any(p.startswith(".github/cargo/") for p in files),
                         ".github/cargo is template-only")
        rust_files = {"deny.toml", "scripts/advisory-db.sh", ".github/workflows/advisories.yml",
                      ".gitmodules", ".github/advisory-db"}
        self.assertEqual(rust_files & files, rust_files if cargo else set())
        self.assertEqual("package-ecosystem: gitsubmodule" in dependabot, cargo)
        for model in ("docs/design/architecture/14-threat-model.md", ".oss-scanner/threat_model.md"):
            self.assertEqual("`scripts/advisory-db.sh`" in
                             (repo / model).read_text(encoding="utf-8"), cargo, model)
        if not cargo:
            return
        self.assertEqual(git(repo, "ls-files", "-s", "--", ".github/advisory-db").split()[:2],
                         ["160000", self.advisory_pin])
        self.assertEqual(git(repo, "config", "-f", ".gitmodules", "submodule.advisory-db.path"),
                         ".github/advisory-db\n")
        self.assertTrue(os.access(repo / "scripts" / "advisory-db.sh", os.X_OK))
        self.assertIn('db-path = "target/advisory-dbs"',
                      (repo / "deny.toml").read_text(encoding="utf-8"))

    def check_calls(self, log: str, repo: Path) -> None:
        for call in EXPECTED_CALLS:
            self.assertTrue(any(line.startswith(call) for line in log.splitlines()),
                            f"init-repo.sh never ran: {call}")
        for call in FORBIDDEN_CALLS:
            self.assertFalse(any(line.startswith(call) for line in log.splitlines()),
                             f"init-repo.sh should not run: {call}")

        security = json.loads(stdin_after(log, f"gh api -X PATCH repos/{REPO} --input -"))
        for key in SECRET_SETTINGS:
            self.assertEqual(security["security_and_analysis"][key], {"status": "enabled"}, key)

        protection = json.loads(stdin_after(log, f"gh api -X PUT repos/{REPO}/branches/main/protection"))
        self.assertTrue(protection["enforce_admins"])
        self.assertTrue(protection["required_conversation_resolution"])
        self.assertFalse(protection["allow_force_pushes"])
        required = protection["required_status_checks"]["contexts"]
        self.assertEqual(required, [c for c in required_checks(ROOT) if c != "template-test"])
        missing = set(required) - reported_checks(repo)
        self.assertEqual(missing, set(), "required checks that no workflow job reports")


if __name__ == "__main__":
    unittest.main()
