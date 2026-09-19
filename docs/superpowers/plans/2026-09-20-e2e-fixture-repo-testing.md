# Automated E2E Testing Against the Live Fixture Repo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `docs/test-strategy.md`'s manual verification checklist into an automated pytest
suite (`tests/e2e/`) that exercises the real GitHub REST API against a persistent, disposable
fixture repo — closing the "no automated end-to-end test" item in `ROADMAP.md`'s "Next" table.

**Architecture:** A new `tests/e2e/` package, excluded from the default `pytest` run via a
registered `e2e` marker, calls repo-policy's real CLI entry points (`validate`/`plan`/`apply`
through `click.testing.CliRunner`, exactly as `tests/test_cli.py` already does for the mocked
suite) against `shipsolid/repo-policy-e2e-fixture` using a real token. Because that repo is one
persistent, shared resource (not created fresh per run), a session-scoped `clean_fixture_repo`
fixture resets it to a known baseline (no branch protection, no rulesets, a second branch for
ruleset-enforcement coverage) before the suite runs and restores that baseline afterward. A new
`workflow_dispatch` + nightly-scheduled GitHub Actions workflow runs the suite in CI; it is
deliberately never triggered by `push`/`pull_request`.

**Tech Stack:** pytest (marker-based opt-in), httpx (raw calls for test-only repo-reset
operations that repo-policy's own `GitHubClient` has no production reason to expose), Click's
`CliRunner`, GitHub Actions (`workflow_dispatch` + `schedule`).

**Spec:** `docs/test-strategy.md` (Manual Verification Checklist + Known Gaps), `ROADMAP.md`
("Automated end-to-end test against a disposable real repo" row), `SECURITY.md` (Threat Model +
Secrets Management — the new workflow's trigger choice must not contradict the documented
`pull_request_target` guidance).

## Global Constraints

- Fixture repo: `shipsolid/repo-policy-e2e-fixture` (public; confirmed via `gh api` — GitHub
  Advanced Security features like `secret_scanning` are free only on public repos for a personal
  account, and this repo already has `secret_scanning`/`secret_scanning_push_protection` verified
  working against it this session).
- Fixture repo currently has exactly one branch (`main`), no branch protection, no rulesets —
  confirmed live via `gh api repos/shipsolid/repo-policy-e2e-fixture/branches` /
  `.../branches/main/protection` / `.../rulesets` immediately before this plan was written. Do
  not assume a `repo-policy-verify` branch already exists — the test suite must create it.
  Ruleset-enforcement branch name: `repo-policy-verify` (matches the manual-verification naming
  used earlier this session).
- CI secret: `REPO_POLICY_E2E_TOKEN`, already created (fine-grained PAT, `Administration: Read
  and write`, resource owner `shipsolid`, single-repo access to
  `shipsolid/repo-policy-e2e-fixture`) and already registered as a repo secret on
  `shipsolid/repo-policy` — confirmed via `gh secret list --repo shipsolid/repo-policy`. Do not
  create a new secret; reference this one.
- Ruleset naming convention: `repo-policy:{branch}` — confirmed in
  `src/repo_policy/policies/rulesets.py:8` (`_ruleset_name`) and `src/repo_policy/apply.py:102`
  (prune logic). The pruned ruleset in this plan's tests is therefore named exactly
  `repo-policy:repo-policy-verify`.
- pytest marker name: `e2e`. Registered in `pyproject.toml`'s `[tool.pytest.ini_options]` with
  `addopts = "-m 'not e2e'"` so a bare `pytest` (used by `.github/workflows/ci.yml` and every
  local dev run) excludes it by default; `pytest -m e2e` opts in explicitly.
- Token env var read by the new suite: `REPO_POLICY_E2E_TOKEN`. If unset, tests under the `e2e`
  marker must **skip with a clear reason**, never fail or error.
- `GitHubClient` (`src/repo_policy/github_client.py`) gets **no new methods** for this plan —
  branch creation and unconditional protection removal are test-fixture-reset concerns, not
  production repo-policy concerns (repo-policy's own documented limitation, see `ROADMAP.md`
  "Later": it cannot fully "release" a branch from management). Test-only reset logic uses a
  separate raw `httpx.Client` fixture instead of extending the production class.
- New workflow triggers: `workflow_dispatch` and `schedule` (nightly, `cron: "0 3 * * *"`) only —
  never `push` or `pull_request`/`pull_request_target`, per `SECURITY.md`'s Threat Model row on
  `pull_request_target` misuse and the general "don't hammer a shared real repo on every commit"
  reasoning already implicit in that doc.
- Exact CLI output strings this plan's assertions depend on (verified by reading
  `src/repo_policy/cli.py` and `src/repo_policy/render.py` before writing this plan — do not
  re-derive, they are exact):
  - `render_plan` (`src/repo_policy/render.py:33-53`): a fully-compliant branch's block ends with
    the literal line `No changes required.`; drift blocks start with `Repository: {repo}` and
    `Branch: {branch}`.
  - `cli.apply` (`src/repo_policy/cli.py:155-159`): always exits `0`; per-branch line is either
    `f"{branch}: applied {n} change(s)"` or `f"{branch}: no changes needed"`.
  - `cli.apply`'s strict-mode pruning line (`src/repo_policy/cli.py:149`):
    `f"- removed orphaned ruleset {deleted_name}"` — note the leading `"- "`.
  - `cli._run_check`'s `audit`-only (`render=False`) compliant message
    (`src/repo_policy/cli.py:108-109`): `f"{resolved_repo} is compliant."` — this text does
    **not** appear for `plan` (`render=True`); do not assert it against `plan` output.
- Live verification caveat: this session's shell does not have `REPO_POLICY_E2E_TOKEN` exported
  (confirmed via `[ -n "$REPO_POLICY_E2E_TOKEN" ]`), so the skip-without-token path can be
  verified directly during implementation, but full live-network verification of the lifecycle
  tests requires either the user exporting the token into the implementation shell for a manual
  run, or waiting for the first real run of the new CI workflow. Each task below says explicitly
  which verification is possible without the token and which is deferred.

---

### Task 1: E2E marker infrastructure + live-repo connectivity fixtures

**Files:**
- Modify: `pyproject.toml` (`[tool.pytest.ini_options]`)
- Create: `tests/e2e/__init__.py` (empty — makes `tests/e2e` an explicit package so the module
  path `tests.e2e.conftest` is unambiguous)
- Create: `tests/e2e/conftest.py`
- Create: `tests/e2e/test_fixture_repo.py` (first test only; more tests land in Task 3)

**Interfaces:**
- Produces: `e2e_token` (session-scoped fixture, `str`, skips the requesting test if
  `REPO_POLICY_E2E_TOKEN` is unset), `live_client` (session-scoped fixture, `GitHubClient`,
  depends on `e2e_token`), `raw_http` (session-scoped fixture, `httpx.Client`, depends on
  `e2e_token`) — all three consumed by Task 2 and Task 3.
- Consumes: `repo_policy.github_client.GitHubClient` (existing, unmodified).

- [ ] **Step 1: Write `tests/e2e/__init__.py`**

Empty file:

```python
```

- [ ] **Step 2: Write `tests/e2e/conftest.py`**

```python
from __future__ import annotations

import os
from collections.abc import Iterator

import httpx
import pytest

from repo_policy.github_client import GitHubClient

LIVE_OWNER = "shipsolid"
LIVE_NAME = "repo-policy-e2e-fixture"
LIVE_REPO = f"{LIVE_OWNER}/{LIVE_NAME}"
RULESET_BRANCH = "repo-policy-verify"


@pytest.fixture(scope="session")
def e2e_token() -> str:
    token = os.environ.get("REPO_POLICY_E2E_TOKEN")
    if not token:
        pytest.skip(
            "REPO_POLICY_E2E_TOKEN not set -- skipping E2E tests against the live fixture "
            f"repo ({LIVE_REPO}); export it to run this suite locally"
        )
    return token


@pytest.fixture(scope="session")
def live_client(e2e_token: str) -> Iterator[GitHubClient]:
    with GitHubClient(token=e2e_token, owner=LIVE_OWNER, repo=LIVE_NAME) as client:
        yield client


@pytest.fixture(scope="session")
def raw_http(e2e_token: str) -> Iterator[httpx.Client]:
    """Raw client for test-only repo-reset calls (unconditional protection removal, branch
    creation) that repo-policy's own GitHubClient has no production reason to expose -- see
    this plan's Global Constraints."""
    with httpx.Client(
        base_url="https://api.github.com",
        headers={
            "Authorization": f"Bearer {e2e_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30.0,
    ) as client:
        yield client


def _strip_protection_and_rulesets(live_client: GitHubClient, raw_http: httpx.Client) -> None:
    for branch in ("main", RULESET_BRANCH):
        response = raw_http.delete(f"/repos/{LIVE_OWNER}/{LIVE_NAME}/branches/{branch}/protection")
        assert response.status_code in (204, 404), response.text

    for summary in live_client.list_rulesets():
        live_client.delete_ruleset(summary["id"])


def _ensure_ruleset_branch_exists(raw_http: httpx.Client) -> None:
    ref_response = raw_http.get(f"/repos/{LIVE_OWNER}/{LIVE_NAME}/git/ref/heads/{RULESET_BRANCH}")
    if ref_response.status_code == 200:
        return
    assert ref_response.status_code == 404, ref_response.text

    main_response = raw_http.get(f"/repos/{LIVE_OWNER}/{LIVE_NAME}/branches/main")
    assert main_response.status_code == 200, main_response.text
    main_sha = main_response.json()["commit"]["sha"]

    create_response = raw_http.post(
        f"/repos/{LIVE_OWNER}/{LIVE_NAME}/git/refs",
        json={"ref": f"refs/heads/{RULESET_BRANCH}", "sha": main_sha},
    )
    assert create_response.status_code == 201, create_response.text


@pytest.fixture(scope="session")
def clean_fixture_repo(live_client: GitHubClient, raw_http: httpx.Client) -> Iterator[None]:
    """Resets shipsolid/repo-policy-e2e-fixture to a known baseline once per test session: no
    branch protection, no rulesets, and a second branch (repo-policy-verify) for
    ruleset-enforcement coverage. This is a persistent, shared, real repo reused across every
    local and CI run -- not created fresh per run -- so tests cannot assume a blank slate without
    this fixture. See docs/test-strategy.md's E2E section."""
    _strip_protection_and_rulesets(live_client, raw_http)
    _ensure_ruleset_branch_exists(raw_http)
    yield
    _strip_protection_and_rulesets(live_client, raw_http)
```

- [ ] **Step 3: Write the connectivity smoke test in `tests/e2e/test_fixture_repo.py`**

```python
from __future__ import annotations

import pytest

from tests.e2e.conftest import LIVE_REPO

pytestmark = pytest.mark.e2e


def test_live_token_and_repo_are_reachable(live_client):
    repo = live_client.get_repo()
    assert repo["full_name"] == LIVE_REPO
```

- [ ] **Step 4: Register the `e2e` marker and exclude it by default**

In `pyproject.toml`, change:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

to:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "e2e: exercises the real GitHub API against the live shipsolid/repo-policy-e2e-fixture repo (requires REPO_POLICY_E2E_TOKEN); excluded by default, opt in with -m e2e",
]
addopts = "-m 'not e2e'"
```

- [ ] **Step 5: Verify the skip-without-token path (no live token required)**

Run: `pytest -m e2e -v tests/e2e/test_fixture_repo.py`
Expected: `test_live_token_and_repo_are_reachable` reported as **SKIPPED**, with the reason text
containing `REPO_POLICY_E2E_TOKEN not set`. Exit code `0` (skips aren't failures).

- [ ] **Step 6: Verify default exclusion doesn't break the existing suite**

Run: `pytest -v`
Expected: same pass count as before this task (no `e2e`-marked test runs or is even attempted);
confirm the new `tests/e2e/test_fixture_repo.py` file does not appear in the run's output.

- [ ] **Step 7: If a live token is available, verify connectivity for real**

Only if `REPO_POLICY_E2E_TOKEN` can be exported into this shell (ask the user if it's not
already present — see this plan's Global Constraints):

Run: `REPO_POLICY_E2E_TOKEN=<token> pytest -m e2e -v tests/e2e/test_fixture_repo.py`
Expected: `test_live_token_and_repo_are_reachable` **PASSES**. If it fails with a `401`/`403`,
stop and report — it means the PAT's scope or resource owner is wrong, not a code bug.

- [ ] **Step 8: Run ruff and mypy**

Run: `ruff check src tests` and `mypy src`
Expected: both clean. (`tests/e2e/` is plain pytest code, not type-checked by `mypy src`, which
only targets `src/` — consistent with the existing `tests/` directory.)

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml tests/e2e/__init__.py tests/e2e/conftest.py tests/e2e/test_fixture_repo.py
git commit -m "test: add e2e marker infrastructure and live fixture-repo connectivity check"
```

---

### Task 2: E2E fixture policy files + validate coverage

**Files:**
- Create: `tests/e2e/fixtures/e2e_full_policy.yml`
- Create: `tests/e2e/fixtures/e2e_prune_policy.yml`
- Modify: `tests/e2e/test_fixture_repo.py`

**Interfaces:**
- Consumes: `LIVE_REPO`, `RULESET_BRANCH` (from `tests/e2e/conftest.py`, Task 1).
- Produces: `FULL_POLICY` / `PRUNE_POLICY` path constants in `tests/e2e/test_fixture_repo.py`,
  consumed by Task 3's lifecycle tests.

- [ ] **Step 1: Write `tests/e2e/fixtures/e2e_full_policy.yml`**

Modeled directly on this session's manual-verification fixture (`verify.policy.yml`), covering
all 11 branch-level fields (`main`, `branch_protection`) plus the 5 ruleset-compatible fields
(`repo-policy-verify`, `ruleset`) plus all 7 repo-level settings:

```yaml
version: 1

branches:
  main:
    enforcement: branch_protection
    pull_requests:
      required: true
      approvals: 1
      code_owner_review: false
      dismiss_stale_reviews: true
      require_last_push_approval: true
    linear_history: true
    allow_force_push: false
    allow_deletion: false
    enforce_admins: true
    required_conversation_resolution: true
    lock_branch: false
    allow_fork_syncing: false
    clear_restrictions: true

  repo-policy-verify:
    enforcement: ruleset
    pull_requests:
      required: true
      approvals: 1
      code_owner_review: false
      dismiss_stale_reviews: true
      require_last_push_approval: true
    linear_history: true
    allow_force_push: false
    allow_deletion: false

repo_settings:
  delete_branch_on_merge: true
  allow_update_branch: true
  vulnerability_alerts: true
  automated_security_fixes: true
  private_vulnerability_reporting: true
  secret_scanning: true
  secret_scanning_push_protection: true
```

- [ ] **Step 2: Write `tests/e2e/fixtures/e2e_prune_policy.yml`**

Modeled on this session's manual-verification prune fixture (`verify-prune.policy.yml`): same
`main` branch, `strict: true`, and the `repo-policy-verify` branch entry removed entirely so
`apply --strict` has an orphaned ruleset to prune:

```yaml
version: 1
strict: true

branches:
  main:
    enforcement: branch_protection
    pull_requests:
      required: true
      approvals: 1
      code_owner_review: false
      dismiss_stale_reviews: true
      require_last_push_approval: true
    linear_history: true
    allow_force_push: false
    allow_deletion: false
    enforce_admins: true
    required_conversation_resolution: true
    lock_branch: false
    allow_fork_syncing: false
    clear_restrictions: true
```

- [ ] **Step 3: Add the validate test and path constants to `tests/e2e/test_fixture_repo.py`**

Replace the file's contents with:

```python
from __future__ import annotations

import pytest
from click.testing import CliRunner

from repo_policy.cli import main
from tests.e2e.conftest import LIVE_REPO

pytestmark = pytest.mark.e2e

FULL_POLICY = "tests/e2e/fixtures/e2e_full_policy.yml"
PRUNE_POLICY = "tests/e2e/fixtures/e2e_prune_policy.yml"


def _invoke(*args: str):
    return CliRunner().invoke(main, list(args))


def test_validate_accepts_e2e_fixture_policies():
    for config in (FULL_POLICY, PRUNE_POLICY):
        result = _invoke("validate", "--config", config)
        assert result.exit_code == 0, result.output


def test_live_token_and_repo_are_reachable(live_client):
    repo = live_client.get_repo()
    assert repo["full_name"] == LIVE_REPO
```

- [ ] **Step 4: Run the no-network-required test**

Run: `pytest -m e2e -v tests/e2e/test_fixture_repo.py::test_validate_accepts_e2e_fixture_policies`
Expected: **PASSES** — this test needs no token or network access at all (`validate` is pure
local YAML/schema checking), so it runs regardless of `REPO_POLICY_E2E_TOKEN`.

- [ ] **Step 5: Run ruff and mypy**

Run: `ruff check src tests` and `mypy src`
Expected: both clean.

- [ ] **Step 6: Commit**

```bash
git add tests/e2e/fixtures/e2e_full_policy.yml tests/e2e/fixtures/e2e_prune_policy.yml tests/e2e/test_fixture_repo.py
git commit -m "test: add e2e fixture policy files modeled on this session's manual verification"
```

---

### Task 3: Full lifecycle E2E tests (drift, apply, idempotency, strict prune)

**Files:**
- Modify: `tests/e2e/test_fixture_repo.py`

**Interfaces:**
- Consumes: `clean_fixture_repo`, `live_client`, `e2e_token` (Task 1's `conftest.py`);
  `FULL_POLICY`, `PRUNE_POLICY`, `_invoke` (Task 2, same file).
- Produces: nothing consumed by later tasks — this is the leaf test layer.

- [ ] **Step 1: Add the four lifecycle tests**

Append to `tests/e2e/test_fixture_repo.py` (after `test_live_token_and_repo_are_reachable`):

```python
def test_plan_reports_full_drift_on_unprotected_branches(clean_fixture_repo, e2e_token):
    result = _invoke("plan", "--config", FULL_POLICY, "--repo", LIVE_REPO, "--token", e2e_token)
    assert result.exit_code == 1, result.output
    assert "Branch: main" in result.output
    assert "Branch: repo-policy-verify" in result.output


def test_apply_full_policy_succeeds(clean_fixture_repo, e2e_token):
    result = _invoke("apply", "--config", FULL_POLICY, "--repo", LIVE_REPO, "--token", e2e_token)
    assert result.exit_code == 0, result.output


def test_plan_reports_zero_drift_after_apply(clean_fixture_repo, e2e_token):
    """Must run after test_apply_full_policy_succeeds (same session-scoped clean_fixture_repo,
    same fixture repo) -- proves real-world idempotency against a live repo, the exact gap
    docs/test-strategy.md's Known Gaps previously described as manual-only."""
    result = _invoke("plan", "--config", FULL_POLICY, "--repo", LIVE_REPO, "--token", e2e_token)
    assert result.exit_code == 0, result.output
    assert result.output.count("No changes required.") == 2


def test_strict_apply_prunes_orphaned_ruleset(clean_fixture_repo, e2e_token, live_client):
    """Must run after test_apply_full_policy_succeeds -- the repo-policy:repo-policy-verify
    ruleset must already exist (created by that apply) for pruning to have something to prune."""
    before = live_client.find_ruleset_by_name("repo-policy:repo-policy-verify")
    assert before is not None, "precondition failed: expected ruleset from the prior apply"

    result = _invoke("apply", "--config", PRUNE_POLICY, "--repo", LIVE_REPO, "--token", e2e_token)

    assert result.exit_code == 0, result.output
    assert "- removed orphaned ruleset repo-policy:repo-policy-verify" in result.output
    after = live_client.find_ruleset_by_name("repo-policy:repo-policy-verify")
    assert after is None
```

Note on ordering: pytest runs tests within a module in definition order by default (no
randomization plugin is installed — confirmed via `pyproject.toml`'s `[project.optional-dependencies].dev`,
which lists only `pytest`, `respx`, `ruff`, `mypy`). These four tests are written in the exact
sequence they must execute in: drift → apply → zero-drift → prune. Each requests
`clean_fixture_repo` explicitly (a session-scoped fixture pytest evaluates once and reuses, not
once per test) so the dependency is self-documenting rather than relying on file order alone.

- [ ] **Step 2: Verify locally without a token (skip path only)**

Run: `pytest -m e2e -v tests/e2e/test_fixture_repo.py`
Expected: `test_validate_accepts_e2e_fixture_policies` **PASSES**; every other test **SKIPS**
with the `REPO_POLICY_E2E_TOKEN not set` reason. No failures or errors.

- [ ] **Step 3: If a live token is available, run the full lifecycle for real**

Only if `REPO_POLICY_E2E_TOKEN` can be exported into this shell:

Run: `REPO_POLICY_E2E_TOKEN=<token> pytest -m e2e -v tests/e2e/test_fixture_repo.py`
Expected: all 6 tests **PASS**, in the order listed above. If
`test_plan_reports_full_drift_on_unprotected_branches` fails because the repo unexpectedly
already has protection/rulesets from a prior interrupted run, that is exactly what
`clean_fixture_repo` exists to prevent — investigate rather than loosening the assertion.

- [ ] **Step 4: Run the full existing suite plus ruff and mypy**

Run: `pytest -v` (confirms the default run still excludes `tests/e2e/`), then
`pytest -m e2e -v`, then `ruff check src tests`, then `mypy src`.
Expected: all clean.

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/test_fixture_repo.py
git commit -m "test: add full E2E lifecycle coverage against the live fixture repo"
```

---

### Task 4: Nightly/manual GitHub Actions workflow

**Files:**
- Create: `.github/workflows/e2e.yml`

**Interfaces:**
- Consumes: the `e2e` pytest marker (Task 1), the `REPO_POLICY_E2E_TOKEN` repo secret (already
  exists — see Global Constraints).

- [ ] **Step 1: Write `.github/workflows/e2e.yml`**

```yaml
name: E2E (live fixture repo)

on:
  workflow_dispatch:
  schedule:
    - cron: "0 3 * * *"

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: pytest -m e2e -v
        env:
          REPO_POLICY_E2E_TOKEN: ${{ secrets.REPO_POLICY_E2E_TOKEN }}
```

- [ ] **Step 2: Validate workflow YAML syntax**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/e2e.yml'))"`
Expected: no exception (confirms valid YAML before it's ever run by GitHub Actions).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/e2e.yml
git commit -m "ci: add nightly/manual E2E workflow against the live fixture repo"
```

Note: this workflow cannot be exercised end-to-end until it's pushed and either its schedule
fires or someone runs `gh workflow run e2e.yml`/uses the Actions UI — both require a push to a
branch GitHub Actions is configured to run workflows from. Do not attempt to fake-run it locally;
Step 2's YAML-syntax check plus Task 1-3's local `pytest -m e2e` runs are the pre-merge
verification for this task.

---

### Task 5: Documentation updates

**Files:**
- Modify: `docs/test-strategy.md`
- Modify: `ROADMAP.md`
- Modify: `SECURITY.md`

**Interfaces:**
- Consumes: nothing (docs-only task, no code interfaces).

- [ ] **Step 1: Get the current, real test counts (don't guess)**

Run: `pytest --collect-only -q | tail -3` and `pytest -m e2e --collect-only -q | tail -3`
Record the two numbers (default-suite count, e2e-suite count) for use in Step 2 — the existing
`docs/test-strategy.md` "121 tests" figure is already stale (pre-dates 4 phases shipped earlier
this session); fix it to the real current count while editing this paragraph anyway.

- [ ] **Step 2: Update `docs/test-strategy.md`'s Test Pyramid section**

Replace the opening paragraph (currently: `121 tests, all unit-level, ... No end-to-end tests run
in CI — the true end-to-end verification for this project is manual, against a real repository,
documented below.`) with the real counts from Step 1 and a mention of the new `tests/e2e/`
package, e.g.:

```markdown
<N> unit-level tests (mocked via `respx`), organized one file per source module
(`tests/test_<module>.py`) plus `tests/test_idempotency.py` (one integration-shaped test) and
`tests/test_policies_parity.py` (a cross-backend regression guard) — plus <M> end-to-end tests in
`tests/e2e/` that exercise the real GitHub API against a live, persistent fixture repo
(`shipsolid/repo-policy-e2e-fixture`). The E2E suite is excluded from the default `pytest` run
(pytest marker `e2e`); run it explicitly with `pytest -m e2e` (requires
`REPO_POLICY_E2E_TOKEN`), or via the nightly/manual `.github/workflows/e2e.yml`.
```

- [ ] **Step 3: Update the Manual Verification Checklist section**

Add a note directly above the numbered checklist:

```markdown
Steps 1–7 below are now automated in `tests/e2e/test_fixture_repo.py` (run via `pytest -m e2e`,
or the nightly `.github/workflows/e2e.yml`) — see
`docs/superpowers/plans/2026-09-20-e2e-fixture-repo-testing.md`. This checklist remains as the
human-readable reference and manual fallback for anyone without CI access to the fixture repo.
```

- [ ] **Step 4: Update the Known Gaps section**

Change:

```markdown
- No automated end-to-end test against a real GitHub repository — the checklist above is manual.
  Automating it would require a disposable-repo-per-run fixture and a real, least-privilege PAT in
  CI secrets; deferred (see `ROADMAP.md`).
```

to:

```markdown
- ~~No automated end-to-end test against a real GitHub repository~~ — closed: see `tests/e2e/`
  and `.github/workflows/e2e.yml`.
```

Leave the other two Known Gaps bullets (`No CI-enforced coverage threshold`, `No test exercises
GitHub's classic-branch-protection-specific edge cases beyond what's modeled`) unchanged — this
plan does not address either.

- [ ] **Step 5: Move the ROADMAP.md item from Next to Now**

In `ROADMAP.md`, remove this row from the `## Next` table:

```markdown
| Automated end-to-end test against a disposable real repo | Close the gap the manual checklist in `docs/test-strategy.md` currently covers by hand | a scoped CI PAT + disposable-repo fixture | TBD    |
```

and add this row to the `## Now` table (matching the existing rows' column style exactly):

```markdown
| Automated end-to-end test against a disposable real repo | Closes the last manual-only gap in `docs/test-strategy.md`; runs nightly/on-demand against `shipsolid/repo-policy-e2e-fixture` via `.github/workflows/e2e.yml` | shipped | TBD |
```

Also update the `> Last updated` line at the top of `ROADMAP.md` to today's date.

- [ ] **Step 6: Update `SECURITY.md`'s Secrets Management section**

Add a bullet after the existing three:

```markdown
- A second, narrower-scoped PAT (`REPO_POLICY_E2E_TOKEN`) exists for the automated E2E suite
  (`tests/e2e/`, `.github/workflows/e2e.yml`): fine-grained, `Administration: Read and write`,
  restricted to the single disposable fixture repo (`shipsolid/repo-policy-e2e-fixture`). Its
  blast radius is bounded to that one repo — a concrete instance of the "scope the PAT as
  narrowly as GitHub allows" mitigation already listed in the Threat Model below, not a new
  category of risk.
```

- [ ] **Step 7: Commit**

```bash
git add docs/test-strategy.md ROADMAP.md SECURITY.md
git commit -m "docs: record the automated E2E suite against the live fixture repo"
```

---

## Self-Review Notes

- **Spec coverage:** `docs/test-strategy.md`'s Manual Verification Checklist steps 1–7 are all
  covered — 1 (`validate`) in Task 2, 2–4 (`plan` drift, `apply`, `plan` zero-drift) in Task 3,
  5 (repeat with `enforcement: ruleset`) is bundled into the same full-policy run rather than a
  separate repeat, since both branches are declared together in `e2e_full_policy.yml`, 6 (strict
  prune) in Task 3, 7 (restore) via `clean_fixture_repo`'s teardown in Task 1. `ROADMAP.md`'s
  "Next" row dependency (scoped CI PAT + disposable-repo fixture) was already satisfied before
  this plan was written (see Global Constraints) — this plan's job was only the automation
  itself. `SECURITY.md`'s `pull_request_target` guidance is honored by Task 4's trigger choice.
- **Placeholder scan:** no "TBD"/"handle it later"/unshown code — every step has literal file
  content. The only deferred items (Task 1 Step 7, Task 3 Step 3 "if a live token is available")
  are explicitly conditional on a credential this plan's author does not hold, not vague
  hand-waving — the unconditional steps (skip-path verification, ruff, mypy, the token-free
  `validate` test) fully verify each task without it.
- **Type consistency:** `clean_fixture_repo`/`live_client`/`raw_http`/`e2e_token` fixture names
  and signatures are identical everywhere they're referenced across Tasks 1–3. `LIVE_REPO`,
  `FULL_POLICY`, `PRUNE_POLICY` are defined once (Task 1's `conftest.py` for `LIVE_REPO`; Task
  2's `test_fixture_repo.py` for the policy paths) and only ever imported/reused after that,
  never redefined with a different value.
