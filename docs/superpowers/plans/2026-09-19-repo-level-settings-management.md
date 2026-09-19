# Repo-Level Settings Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional, repo-wide `repo_settings:` section to `policy.yml` that manages five
GitHub settings repo-policy doesn't touch today: `delete_branch_on_merge`, `allow_update_branch`,
`vulnerability_alerts` (Dependabot alerts), `automated_security_fixes` (Dependabot security
updates), `private_vulnerability_reporting`, `secret_scanning`, and `secret_scanning_push_protection`
(7 fields total).

**Architecture:** These fields are repo-wide, not per-branch, so they get a parallel path rather
than being shoehorned into the existing `BranchPolicy`/`diff._FIELDS` machinery: a new
`RepoSettingsPolicy` model, a pure-translation module (`policies/repo_settings.py`, no I/O — mirrors
`policies/branch_protection.py`'s split), and a new orchestration module (`repo_settings.py` at the
package root — mirrors `apply.py`'s split). GitHub exposes these seven fields across four different
endpoint shapes (one flat PATCH pair, one nested-PATCH pair, and three independent GET/PUT toggle
endpoints), so translation is three small, focused functions rather than one shared
`from_api`/`to_api_payload` pair. A 422 response means "not available on this repo" (no GitHub
Advanced Security license, or an eligibility restriction) for two of the endpoint groups — an
`unavailable` outcome, not a failure — which `GitHubClient._request` doesn't have a concept of
today; it gets one new `allow_422` parameter, mirroring the existing `allow_404`.

**Amendment (found while executing Task 1, not anticipated when first drafted):** each field is
wired into `plan_repo_settings`/`apply_repo_settings` **only in the task that has both the pure
diff function and the live `GitHubClient` method available together** — never partially. The
original draft had Task 1 wire `diff_security_and_analysis`/`to_security_and_analysis_payload` into
orchestration even though `GitHubClient.update_security_and_analysis` doesn't exist until Task 5;
`mypy` caught the resulting `attr-defined` error immediately, and on reflection it would have been a
real bug even if mypy had missed it — `plan` would report `secret_scanning` drift that `apply` could
never actually fix. `policies/repo_settings.py`'s pure functions still all ship in Task 1 (cheap,
no I/O, fully unit-tested there), but their orchestration wiring moves to Task 5, alongside the
client method that makes them usable end-to-end.

**Tech Stack:** Python 3.10+, Pydantic v2, httpx, pytest — same stack as Phase 1
(`docs/superpowers/plans/2026-09-19-branch-protection-field-parity.md`), no new dependencies.

**Spec:** No separate spec doc. Scoped directly from a verbatim read of the reference
implementation's exact GitHub API contract — `/home/amit/repos/McCainFoods/sre-observability-gates/repo_security/{apply,github_client,diff}.py`
(not part of this repo) — cross-checked against repo-policy's own current `src/repo_policy/*.py`
(read in full as of the Phase 1 merge, commit `fde8be8`) and `ARCHITECTURE.md`/`docs/adrs/0003-*`.

## Global Constraints

- Every field is optional (`None` = not declared = never touched, zero API calls for that field) —
  matches `ADR-0003`'s managed-scope philosophy exactly: nothing in `repo_settings:` is enforced
  unless a human explicitly wrote it in `policy.yml`.
- **`repo_settings:` does not participate in `strict` mode.** Branch-level `strict` resets
  *undeclared* fields to a permissive schema default (`ADR-0003`) — there's no equivalent universal
  "permissive baseline" for e.g. `delete_branch_on_merge` that would be safe to auto-apply, and the
  reference implementation itself has no managed-scope/strict distinction at all (it always enforces
  a fixed baseline, full stop). Scoping `repo_settings` to managed-scope-only for v1 is a deliberate,
  documented decision, not an oversight — call this out explicitly in Task 6's docs update.
- **Zero API calls when `policy.yml` has no `repo_settings:` section at all** — not even
  `GET /repos/{owner}/{repo}`. Every existing `policy.yml` in production today has no
  `repo_settings:` key; this must be a complete no-op for them, matching the idempotency guarantee
  `ARCHITECTURE.md` already documents for branch-level `apply`.
- **A field is wired into `plan_repo_settings`/`apply_repo_settings` only in the task where its
  live `GitHubClient` method also ships** — never split across tasks, per the Amendment above.
- `automated_security_fixes: true` requires `vulnerability_alerts: true` also be declared in the
  same `policy.yml` — GitHub rejects enabling Dependabot security updates before Dependabot alerts.
  Enforced by a Pydantic model validator on `RepoSettingsPolicy` at `validate`/parse time (fail
  loud, before any API call), not discovered as a live 422.
- Every commit message follows Conventional Commits (`feat: ...`); never hand-edit `CHANGELOG.md`
  (`python-semantic-release` generates it — see `docs/ci-cd.md`).
- TDD throughout: failing test first, for every step that adds behavior.
- Every task's commit must leave `pytest`, `ruff check .`, and `mypy src` all clean — not just the
  plan's final state. Task 1's mypy failure (see Amendment) is exactly the class of bug this
  guards against.

## Verified GitHub API Contract

Extracted verbatim from the reference implementation, not re-derived from memory — use exactly:

| Concern | Method + Path | Success | Special cases |
|---|---|---|---|
| Fetch repo info | `GET /repos/{owner}/{repo}` | 200, JSON body | — |
| `delete_branch_on_merge`, `allow_update_branch` | `PATCH /repos/{owner}/{repo}` with `{"delete_branch_on_merge": bool, "allow_update_branch": bool}` | 200 | Never combine with the `security_and_analysis` PATCH below — a 422 on one must not block the other |
| `secret_scanning`, `secret_scanning_push_protection` | `PATCH /repos/{owner}/{repo}` with `{"security_and_analysis": {"secret_scanning": {"status": "enabled"\|"disabled"}, "secret_scanning_push_protection": {"status": "enabled"\|"disabled"}}}` | 200 | **422 = unavailable** (no GHAS license) — not an error |
| `vulnerability_alerts` (read) | `GET /repos/{owner}/{repo}/vulnerability-alerts` | 204 = enabled | 404 = disabled |
| `vulnerability_alerts` (write) | `PUT /repos/{owner}/{repo}/vulnerability-alerts` (no body) | 204 | — |
| `automated_security_fixes` (read) | `GET /repos/{owner}/{repo}/automated-security-fixes` | 200 JSON `{"enabled": bool}` | 404 = disabled |
| `automated_security_fixes` (write) | `PUT /repos/{owner}/{repo}/automated-security-fixes` (no body) | 204 | — |
| `private_vulnerability_reporting` (read) | `GET /repos/{owner}/{repo}/private-vulnerability-reporting` | 200 JSON `{"enabled": bool}` | **404 or 422 = unavailable** |
| `private_vulnerability_reporting` (write) | `PUT /repos/{owner}/{repo}/private-vulnerability-reporting` (no body) | 204 | **422 = unavailable** |

`GET/PUT /repos/{owner}/{repo}/branches/{branch}/protection` is **not** touched by this plan — that's
Phase 1's territory, already shipped.

---

## File Structure

| File | Responsibility after this plan |
|---|---|
| `src/repo_policy/models.py` | New `RepoSettingsPolicy` model (7 fields + 1 cross-field validator); `PolicyConfig` gains `repo_settings: RepoSettingsPolicy \| None = None` |
| `src/repo_policy/github_client.py` | `_request` gains `allow_422`; 9 new methods (`get_repo`, `update_repo_settings`, `update_security_and_analysis`, `get_vulnerability_alerts`, `enable_vulnerability_alerts`, `get_automated_security_fixes`, `enable_automated_security_fixes`, `get_private_vulnerability_reporting`, `enable_private_vulnerability_reporting`) |
| `src/repo_policy/policies/repo_settings.py` | **New.** Pure diff/translation functions, no I/O — `RepoSettingChange`, `diff_flat_settings`, `to_flat_settings_payload`, `diff_security_and_analysis`, `to_security_and_analysis_payload`, `diff_toggle` — all defined in Task 1, but `diff_security_and_analysis`/`to_security_and_analysis_payload` stay unused by orchestration until Task 5 |
| `src/repo_policy/repo_settings.py` | **New.** Orchestration — `RepoSettingsResult`, `plan_repo_settings`, `apply_repo_settings` |
| `src/repo_policy/render.py` | New `render_repo_settings()` function + `_REPO_SETTINGS_LABELS` dict |
| `src/repo_policy/cli.py` | `_run_check` (audit/plan) and `apply` each gain a repo-settings phase alongside the existing branch loop |
| `tests/test_models.py` | New `RepoSettingsPolicy` tests |
| `tests/test_github_client.py` | New tests for the 9 client methods + `allow_422` |
| `tests/test_policies_repo_settings.py` | **New.** Pure-function tests |
| `tests/test_repo_settings.py` | **New.** Orchestration tests |
| `tests/test_render.py` | New `render_repo_settings` tests |
| `tests/test_cli.py` | New end-to-end CLI wiring tests |
| `tests/fixtures/policy_repo_settings.yml` | **New.** A `policy.yml` fixture with a `repo_settings:` section, for CLI tests |
| `ARCHITECTURE.md` | New Domain Model / Data Flow subsection for repo-level settings |
| `ROADMAP.md` | Remove the "Repo-level security & settings management" bullet from "Later" |

---

### Task 1: Foundation — `delete_branch_on_merge` + `allow_update_branch`

Establishes the entire new architecture end-to-end (schema, client, pure diff, orchestration, CLI,
render) for the simplest pair: one flat `PATCH`, no GHAS-gating, no ordering dependency, no
`unavailable` state. Also defines (but does not yet wire into orchestration) the pure translation
functions Task 5 needs for `secret_scanning`/`secret_scanning_push_protection` — see the Amendment
in this plan's header for why that wiring is deferred.

**Files:**
- Modify: `src/repo_policy/models.py` (new `RepoSettingsPolicy`, `PolicyConfig.repo_settings`)
- Modify: `src/repo_policy/github_client.py` (`get_repo`, `update_repo_settings`)
- Create: `src/repo_policy/policies/repo_settings.py`
- Create: `src/repo_policy/repo_settings.py`
- Modify: `src/repo_policy/render.py` (`render_repo_settings`, `_REPO_SETTINGS_LABELS`)
- Modify: `src/repo_policy/cli.py` (`_run_check`, `apply`)
- Create: `tests/fixtures/policy_repo_settings.yml`
- Test: `tests/test_models.py`, `tests/test_github_client.py`, `tests/test_policies_repo_settings.py` (new), `tests/test_repo_settings.py` (new), `tests/test_render.py`, `tests/test_cli.py`

**Interfaces:**
- Produces: `RepoSettingsPolicy` (models.py); `GitHubClient.get_repo() -> dict`,
  `GitHubClient.update_repo_settings(payload: dict) -> dict` (github_client.py);
  `RepoSettingChange` dataclass, `diff_flat_settings(current_repo: dict, desired: RepoSettingsPolicy) -> list[RepoSettingChange]`,
  `to_flat_settings_payload(changes: list[RepoSettingChange]) -> dict`,
  `diff_security_and_analysis`, `to_security_and_analysis_payload`, `diff_toggle` (all in
  policies/repo_settings.py, the last three unused by orchestration until later tasks);
  `RepoSettingsResult` dataclass, `plan_repo_settings(client, config) -> RepoSettingsResult`,
  `apply_repo_settings(client, config) -> RepoSettingsResult` (repo_settings.py) — every later task
  in this plan extends these same names, never redefines them.

- [ ] **Step 1: Write the failing model tests in `tests/test_models.py`**

```python
from repo_policy.models import RepoSettingsPolicy


def test_repo_settings_policy_defaults_to_all_unset():
    policy = RepoSettingsPolicy()
    assert policy.delete_branch_on_merge is None
    assert policy.allow_update_branch is None


def test_policy_config_repo_settings_defaults_to_none():
    config = PolicyConfig(version=1, branches={})
    assert config.repo_settings is None


def test_policy_config_parses_repo_settings():
    config = PolicyConfig(
        version=1, branches={},
        repo_settings=RepoSettingsPolicy(delete_branch_on_merge=True, allow_update_branch=False),
    )
    assert config.repo_settings.delete_branch_on_merge is True
    assert config.repo_settings.allow_update_branch is False
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_models.py -v -k repo_settings`
Expected: `FAIL` — `RepoSettingsPolicy` doesn't exist yet, `PolicyConfig` has no `repo_settings` field.

- [ ] **Step 3: Add `RepoSettingsPolicy` and wire it into `PolicyConfig` in `src/repo_policy/models.py`**

```python
class RepoSettingsPolicy(BaseModel):
    delete_branch_on_merge: bool | None = None
    allow_update_branch: bool | None = None
    vulnerability_alerts: bool | None = None
    automated_security_fixes: bool | None = None
    private_vulnerability_reporting: bool | None = None
    secret_scanning: bool | None = None
    secret_scanning_push_protection: bool | None = None

    @model_validator(mode="after")
    def _automated_security_fixes_requires_vulnerability_alerts(self) -> RepoSettingsPolicy:
        if self.automated_security_fixes is True and self.vulnerability_alerts is not True:
            raise ValueError(
                "automated_security_fixes: true requires vulnerability_alerts: true to also be "
                "declared -- GitHub rejects enabling Dependabot security updates before Dependabot "
                "alerts are enabled"
            )
        return self
```

(This model validator is used by Task 3, not this task — declaring it now, alongside the model
itself, avoids a second edit to this class later. It has no effect on this task's two fields. Use
the bare `RepoSettingsPolicy` return annotation, not a quoted string — `models.py` already has
`from __future__ import annotations` at the top, so a quoted forward reference is redundant and
`ruff`'s `UP037` rule flags it, exactly as it did once already in Phase 1.)

Add to `PolicyConfig`:

```python
class PolicyConfig(BaseModel):
    version: int
    strict: bool = False
    branches: dict[str, BranchPolicy]
    repo_settings: RepoSettingsPolicy | None = None
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_models.py -v -k repo_settings`
Expected: `PASS`

- [ ] **Step 5: Write the failing client tests in `tests/test_github_client.py`**

This file's real convention (confirmed by reading it): a module-level `client` fixture, and
`@respx.mock`-decorated test functions that call `respx.get(...)`/`respx.patch(...)`/etc. directly
(not a `respx_mock` fixture parameter). Add, right after `test_delete_ruleset_calls_delete`:

```python
@respx.mock
def test_get_repo(client):
    respx.get("https://api.github.com/repos/acme/widgets").mock(
        return_value=httpx.Response(200, json={"default_branch": "main", "delete_branch_on_merge": False})
    )
    data = client.get_repo()
    assert data["default_branch"] == "main"


@respx.mock
def test_update_repo_settings(client):
    route = respx.patch("https://api.github.com/repos/acme/widgets").mock(
        return_value=httpx.Response(200, json={"delete_branch_on_merge": True})
    )
    data = client.update_repo_settings({"delete_branch_on_merge": True})
    assert data["delete_branch_on_merge"] is True
    assert route.calls[0].request.content == b'{"delete_branch_on_merge":true}'
```

- [ ] **Step 6: Run to verify failure**

Run: `pytest tests/test_github_client.py -v -k "get_repo or update_repo_settings"`
Expected: `FAIL` — methods don't exist.

- [ ] **Step 7: Add the two client methods to `src/repo_policy/github_client.py`**

Add after `set_required_signatures` (before `list_rulesets`):

```python
    def get_repo(self) -> dict:
        response = self._request("GET", f"/repos/{self.owner}/{self.repo}")
        return _expect_response(response).json()

    def update_repo_settings(self, payload: dict) -> dict:
        response = self._request("PATCH", f"/repos/{self.owner}/{self.repo}", json=payload)
        return _expect_response(response).json()
```

- [ ] **Step 8: Run to verify pass**

Run: `pytest tests/test_github_client.py -v -k "get_repo or update_repo_settings"`
Expected: `PASS`

- [ ] **Step 9: Write the failing pure-function tests — create `tests/test_policies_repo_settings.py`**

```python
from repo_policy.models import RepoSettingsPolicy
from repo_policy.policies import repo_settings


def test_diff_flat_settings_detects_change():
    current_repo = {"delete_branch_on_merge": False, "allow_update_branch": True}
    desired = RepoSettingsPolicy(delete_branch_on_merge=True)
    changes = repo_settings.diff_flat_settings(current_repo, desired)
    assert len(changes) == 1
    assert changes[0].field == "delete_branch_on_merge"
    assert changes[0].current_value is False
    assert changes[0].desired_value is True
    assert changes[0].action == "add"


def test_diff_flat_settings_skips_undeclared_fields():
    current_repo = {"delete_branch_on_merge": False, "allow_update_branch": False}
    desired = RepoSettingsPolicy(delete_branch_on_merge=True)  # allow_update_branch left unset
    changes = repo_settings.diff_flat_settings(current_repo, desired)
    assert len(changes) == 1
    assert changes[0].field == "delete_branch_on_merge"


def test_diff_flat_settings_empty_when_already_compliant():
    current_repo = {"delete_branch_on_merge": True, "allow_update_branch": True}
    desired = RepoSettingsPolicy(delete_branch_on_merge=True, allow_update_branch=True)
    assert repo_settings.diff_flat_settings(current_repo, desired) == []


def test_to_flat_settings_payload_builds_dict_from_changes():
    current_repo = {"delete_branch_on_merge": False, "allow_update_branch": False}
    desired = RepoSettingsPolicy(delete_branch_on_merge=True, allow_update_branch=True)
    changes = repo_settings.diff_flat_settings(current_repo, desired)
    payload = repo_settings.to_flat_settings_payload(changes)
    assert payload == {"delete_branch_on_merge": True, "allow_update_branch": True}


def test_diff_security_and_analysis_detects_change():
    current_repo = {"security_and_analysis": {"secret_scanning": {"status": "disabled"}}}
    desired = RepoSettingsPolicy(secret_scanning=True)
    changes = repo_settings.diff_security_and_analysis(current_repo, desired)
    assert len(changes) == 1
    assert changes[0].field == "secret_scanning"


def test_diff_security_and_analysis_treats_absent_block_as_disabled():
    current_repo = {}
    desired = RepoSettingsPolicy(secret_scanning=True)
    changes = repo_settings.diff_security_and_analysis(current_repo, desired)
    assert len(changes) == 1
    assert changes[0].current_value is False


def test_to_security_and_analysis_payload_builds_status_wrapped_dict():
    current_repo = {
        "security_and_analysis": {"secret_scanning_push_protection": {"status": "enabled"}}
    }
    desired = RepoSettingsPolicy(secret_scanning=True, secret_scanning_push_protection=False)
    changes = repo_settings.diff_security_and_analysis(current_repo, desired)
    payload = repo_settings.to_security_and_analysis_payload(changes)
    assert payload == {
        "secret_scanning": {"status": "enabled"},
        "secret_scanning_push_protection": {"status": "disabled"},
    }


def test_diff_toggle_returns_change_when_different():
    changes = repo_settings.diff_toggle("vulnerability_alerts", False, True)
    assert len(changes) == 1
    assert changes[0].action == "add"


def test_diff_toggle_empty_when_equal():
    assert repo_settings.diff_toggle("vulnerability_alerts", True, True) == []


def test_diff_toggle_empty_when_current_is_none():
    """current_value=None means 'unavailable' -- never produces a Change."""
    assert repo_settings.diff_toggle("private_vulnerability_reporting", None, True) == []


def test_diff_toggle_empty_when_desired_is_none():
    assert repo_settings.diff_toggle("vulnerability_alerts", False, None) == []
```

- [ ] **Step 10: Run to verify failure**

Run: `pytest tests/test_policies_repo_settings.py -v`
Expected: `FAIL` — `repo_policy.policies.repo_settings` doesn't exist.

- [ ] **Step 11: Create `src/repo_policy/policies/repo_settings.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from repo_policy.models import RepoSettingsPolicy

RepoSettingAction = Literal["add", "modify", "remove"]

_FLAT_FIELDS = ("delete_branch_on_merge", "allow_update_branch")
_SECURITY_AND_ANALYSIS_FIELDS = ("secret_scanning", "secret_scanning_push_protection")


@dataclass(frozen=True)
class RepoSettingChange:
    field: str
    current_value: Any
    desired_value: Any
    action: RepoSettingAction


def _classify(current_value: bool, desired_value: bool) -> RepoSettingAction:
    if current_value is False and desired_value is True:
        return "add"
    if current_value is True and desired_value is False:
        return "remove"
    return "modify"


def diff_flat_settings(current_repo: dict, desired: RepoSettingsPolicy) -> list[RepoSettingChange]:
    """delete_branch_on_merge / allow_update_branch -- both bare top-level booleans on the
    GET /repos/{owner}/{repo} response, matched 1:1 by PATCH /repos/{owner}/{repo}."""
    changes: list[RepoSettingChange] = []
    for field_name in _FLAT_FIELDS:
        desired_value = getattr(desired, field_name)
        if desired_value is None:
            continue  # not declared -- managed-scope: don't touch
        current_value = bool(current_repo.get(field_name, False))
        if current_value != desired_value:
            changes.append(RepoSettingChange(
                field_name, current_value, desired_value, _classify(current_value, desired_value)
            ))
    return changes


def to_flat_settings_payload(changes: list[RepoSettingChange]) -> dict:
    return {change.field: change.desired_value for change in changes}


def diff_security_and_analysis(current_repo: dict, desired: RepoSettingsPolicy) -> list[RepoSettingChange]:
    """secret_scanning / secret_scanning_push_protection -- nested under
    security_and_analysis.<field>.status ("enabled"/"disabled") on the repo GET response. Absence
    (the whole block, or one sub-key) is treated as 'disabled' for diff purposes, matching GitHub's
    own documented default; the apply step's 422 handling (wired in Task 5, once
    GitHubClient.update_security_and_analysis exists) distinguishes a real 'unavailable' from a
    normal disabled state. This function is pure and fully tested here in Task 1; only its
    orchestration wiring is deferred."""
    security = current_repo.get("security_and_analysis") or {}
    changes: list[RepoSettingChange] = []
    for field_name in _SECURITY_AND_ANALYSIS_FIELDS:
        desired_value = getattr(desired, field_name)
        if desired_value is None:
            continue
        current_status = (security.get(field_name) or {}).get("status")
        current_value = current_status == "enabled"
        if current_value != desired_value:
            changes.append(RepoSettingChange(
                field_name, current_value, desired_value, _classify(current_value, desired_value)
            ))
    return changes


def to_security_and_analysis_payload(changes: list[RepoSettingChange]) -> dict:
    return {
        change.field: {"status": "enabled" if change.desired_value else "disabled"}
        for change in changes
    }


def diff_toggle(
    field_name: str, current_value: bool | None, desired_value: bool | None
) -> list[RepoSettingChange]:
    """vulnerability_alerts / automated_security_fixes / private_vulnerability_reporting -- each
    is a single independent boolean fetched from its own GET endpoint, not a shared payload shape
    like the two functions above. current_value=None means 'unavailable' and never produces a
    Change -- there's nothing to diff against. Pure and fully tested here in Task 1; first used by
    orchestration in Task 2."""
    if desired_value is None or current_value is None:
        return []
    if current_value == desired_value:
        return []
    return [RepoSettingChange(field_name, current_value, desired_value, _classify(current_value, desired_value))]
```

- [ ] **Step 12: Run to verify pass**

Run: `pytest tests/test_policies_repo_settings.py -v`
Expected: `PASS`

- [ ] **Step 13: Write the failing orchestration tests — create `tests/test_repo_settings.py`**

This codebase's real convention for orchestration tests (confirmed by reading `tests/test_apply.py`):
a plain `unittest.mock.MagicMock()` as the fake `GitHubClient`, with `.return_value` set on the
methods each test needs and `.assert_called_once_with(...)`/`.assert_not_called()` for verification
— no `respx`, no shared fixture.

```python
from unittest.mock import MagicMock

from repo_policy.models import PolicyConfig, RepoSettingsPolicy
from repo_policy.repo_settings import apply_repo_settings, plan_repo_settings


def test_plan_repo_settings_returns_empty_result_when_section_absent():
    client = MagicMock()
    config = PolicyConfig(version=1, branches={})  # no repo_settings declared
    result = plan_repo_settings(client, config)
    assert result.changes == []
    assert result.unavailable == []
    client.get_repo.assert_not_called()


def test_plan_repo_settings_detects_flat_setting_drift():
    client = MagicMock()
    client.get_repo.return_value = {"delete_branch_on_merge": False}
    config = PolicyConfig(
        version=1, branches={}, repo_settings=RepoSettingsPolicy(delete_branch_on_merge=True)
    )
    result = plan_repo_settings(client, config)
    assert len(result.changes) == 1
    assert result.changes[0].field == "delete_branch_on_merge"


def test_apply_repo_settings_calls_update_when_drift_exists():
    client = MagicMock()
    client.get_repo.return_value = {"delete_branch_on_merge": False}
    config = PolicyConfig(
        version=1, branches={}, repo_settings=RepoSettingsPolicy(delete_branch_on_merge=True)
    )
    result = apply_repo_settings(client, config)
    assert result.applied is True
    client.update_repo_settings.assert_called_once_with({"delete_branch_on_merge": True})


def test_apply_repo_settings_is_idempotent_when_already_compliant():
    client = MagicMock()
    client.get_repo.return_value = {"delete_branch_on_merge": True}
    config = PolicyConfig(
        version=1, branches={}, repo_settings=RepoSettingsPolicy(delete_branch_on_merge=True)
    )
    result = apply_repo_settings(client, config)
    assert result.applied is False
    client.update_repo_settings.assert_not_called()
```

- [ ] **Step 14: Run to verify failure**

Run: `pytest tests/test_repo_settings.py -v`
Expected: `FAIL` — `repo_policy.repo_settings` doesn't exist.

- [ ] **Step 15: Create `src/repo_policy/repo_settings.py`**

**Important — do not import or call `diff_security_and_analysis`/`to_security_and_analysis_payload`/
`diff_toggle` here.** Only `diff_flat_settings`/`to_flat_settings_payload` are wired in this task;
the other three ship as pure functions in `policies/repo_settings.py` (Step 11 above) but their
orchestration wiring is deferred to the task that also adds the matching `GitHubClient` method
(Task 2 for `diff_toggle`/`vulnerability_alerts`; Task 5 for the security-and-analysis pair) — see
this plan's header Amendment for why.

```python
from __future__ import annotations

from dataclasses import dataclass, field

from repo_policy.github_client import GitHubClient
from repo_policy.models import PolicyConfig
from repo_policy.policies.repo_settings import (
    RepoSettingChange,
    diff_flat_settings,
    to_flat_settings_payload,
)


@dataclass
class RepoSettingsResult:
    changes: list[RepoSettingChange] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)
    applied: bool = False


def plan_repo_settings(client: GitHubClient, config: PolicyConfig) -> RepoSettingsResult:
    """Read-only: fetch current state and diff against policy.yml's repo_settings section. Makes
    zero API calls and returns an empty result when the section isn't declared at all."""
    desired = config.repo_settings
    if desired is None:
        return RepoSettingsResult()

    result = RepoSettingsResult()
    current_repo = client.get_repo()
    result.changes.extend(diff_flat_settings(current_repo, desired))
    return result


def apply_repo_settings(client: GitHubClient, config: PolicyConfig) -> RepoSettingsResult:
    desired = config.repo_settings
    if desired is None:
        return RepoSettingsResult()

    result = plan_repo_settings(client, config)

    flat_changes = [c for c in result.changes if c.field in ("delete_branch_on_merge", "allow_update_branch")]
    if flat_changes:
        client.update_repo_settings(to_flat_settings_payload(flat_changes))

    result.applied = bool(result.changes)
    return result
```

- [ ] **Step 16: Run to verify pass**

Run: `pytest tests/test_repo_settings.py -v`
Expected: `PASS`

- [ ] **Step 17: Write the failing render test in `tests/test_render.py`**

```python
from repo_policy.repo_settings import RepoSettingsResult
from repo_policy.policies.repo_settings import RepoSettingChange
from repo_policy.render import render_repo_settings


def test_render_repo_settings_reports_no_changes():
    output = render_repo_settings("acme/widgets", RepoSettingsResult())
    assert "No repo-level setting changes required." in output


def test_render_repo_settings_shows_a_change():
    result = RepoSettingsResult(changes=[
        RepoSettingChange("delete_branch_on_merge", False, True, "add"),
    ])
    output = render_repo_settings("acme/widgets", result)
    assert "+ Delete branch on merge" in output
```

- [ ] **Step 18: Run to verify failure**

Run: `pytest tests/test_render.py -v -k repo_settings`
Expected: `FAIL`

- [ ] **Step 19: Add `render_repo_settings` to `src/repo_policy/render.py`**

Add `from repo_policy.repo_settings import RepoSettingsResult` alongside the existing
`from repo_policy.diff import Change` import at the top of the file, and a
`_REPO_SETTINGS_LABELS` dict alongside `_LABELS`:

```python
_REPO_SETTINGS_LABELS = {
    "delete_branch_on_merge": "Delete branch on merge",
    "allow_update_branch": "Allow update branch",
}
```

Then add the function at the end of the file:

```python
def render_repo_settings(repo: str, result: RepoSettingsResult) -> str:
    lines = [f"Repository: {repo}", "Repo-level settings:", ""]

    for change in result.changes:
        symbol = _SYMBOLS[change.action]
        label = _REPO_SETTINGS_LABELS.get(change.field, change.field)
        lines.append(f"{symbol} {label:<28} {change.current_value} → {change.desired_value}")

    for field_name in result.unavailable:
        label = _REPO_SETTINGS_LABELS.get(field_name, field_name)
        lines.append(f"? {label:<28} unavailable on this repository")

    lines.append("")
    if not result.changes and not result.unavailable:
        lines.append("No repo-level setting changes required.")
    else:
        noun = "change" if len(result.changes) == 1 else "changes"
        lines.append(f"{len(result.changes)} {noun} required.")

    return "\n".join(lines)
```

- [ ] **Step 20: Run to verify pass**

Run: `pytest tests/test_render.py -v -k repo_settings`
Expected: `PASS`

- [ ] **Step 21: Create `tests/fixtures/policy_repo_settings.yml`**

```yaml
version: 1

branches: {}

repo_settings:
  delete_branch_on_merge: true
```

- [ ] **Step 22: Write the failing CLI tests in `tests/test_cli.py`**

This file's real convention (confirmed by reading it): `@patch("repo_policy.cli.GitHubClient")`,
`mock_client = mock_client_cls.return_value.__enter__.return_value`, `CliRunner()`, and
`tests/fixtures/policy_*.yml` files. Add:

```python
@patch("repo_policy.cli.GitHubClient")
def test_audit_makes_no_repo_settings_calls_when_section_absent(mock_client_cls):
    """policy_no_requirements.yml has branches but no repo_settings key -- confirms zero extra
    API calls for every existing policy.yml written before this feature existed."""
    mock_client = mock_client_cls.return_value.__enter__.return_value
    mock_client.get_branch_protection.return_value = None
    mock_client.get_required_signatures.return_value = False
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["audit", "--config", "tests/fixtures/policy_no_requirements.yml", "--repo", "acme/widgets", "--token", "t"],
    )
    assert result.exit_code == 0
    mock_client.get_repo.assert_not_called()


@patch("repo_policy.cli.GitHubClient")
def test_plan_renders_repo_settings_drift(mock_client_cls):
    mock_client = mock_client_cls.return_value.__enter__.return_value
    mock_client.get_repo.return_value = {"delete_branch_on_merge": False}
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["plan", "--config", "tests/fixtures/policy_repo_settings.yml", "--repo", "acme/widgets", "--token", "t"],
    )
    assert result.exit_code == 1
    assert "Repo-level settings:" in result.output
    assert "+ Delete branch on merge" in result.output


@patch("repo_policy.cli.GitHubClient")
def test_apply_applies_repo_settings_drift(mock_client_cls):
    mock_client = mock_client_cls.return_value.__enter__.return_value
    mock_client.get_repo.return_value = {"delete_branch_on_merge": False}
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["apply", "--config", "tests/fixtures/policy_repo_settings.yml", "--repo", "acme/widgets", "--token", "t"],
    )
    assert result.exit_code == 0
    mock_client.update_repo_settings.assert_called_once_with({"delete_branch_on_merge": True})
    assert "repo settings: applied 1 change(s)" in result.output
```

- [ ] **Step 23: Run to verify failure**

Run: `pytest tests/test_cli.py -v -k repo_settings`
Expected: `FAIL`

- [ ] **Step 24: Wire up `src/repo_policy/cli.py`**

Add to the imports:

```python
from repo_policy.render import render_plan, render_repo_settings
from repo_policy.repo_settings import apply_repo_settings, plan_repo_settings
```

In `_run_check` (used by both `audit` and `plan`), add a repo-settings phase after the existing
branch loop:

```python
def _run_check(config_path: str, repo: str | None, token: str | None, *, render: bool) -> int:
    try:
        config = load_policy(config_path)
    except ConfigError as exc:
        click.echo(str(exc), err=True)
        return EXIT_CONFIG_ERROR

    resolved_repo = _resolve_repo(repo)
    owner, name = _split_repo(resolved_repo)

    try:
        with GitHubClient(token=_resolve_token(token), owner=owner, repo=name) as client:
            results = audit_all(client, config)
            repo_settings_result = plan_repo_settings(client, config)
    except GitHubAPIError as exc:
        click.echo(str(exc), err=True)
        return EXIT_API_ERROR

    any_drift = False
    for result in results:
        if render:
            click.echo(render_plan(resolved_repo, result.branch, result.changes))
        elif not result.compliant:
            click.echo(f"{result.branch}: {len(result.changes)} change(s) required")
        any_drift = any_drift or not result.compliant

    if repo_settings_result.changes:
        if render:
            click.echo(render_repo_settings(resolved_repo, repo_settings_result))
        else:
            click.echo(f"repo settings: {len(repo_settings_result.changes)} change(s) required")
        any_drift = True

    if not any_drift and not render:
        click.echo(f"{resolved_repo} is compliant.")
    return EXIT_DRIFT if any_drift else EXIT_OK
```

Note what stayed the same: `unavailable` entries never set `any_drift` — they're informational, not
a compliance failure (matches the reference's own documented behavior — see
`docs/repo-security-baseline.md`'s "GHAS and `unavailable` results" section on the McCain side:
"reports that setting as `unavailable` ... rather than failing the run").

In `apply`, add the corresponding phase after the existing branch-apply block:

```python
@main.command()
@click.option("--config", "config_path", default="policy.yml", show_default=True)
@click.option("--repo", default=None)
@click.option("--token", default=None)
def apply(config_path: str, repo: str | None, token: str | None) -> None:
    try:
        config = load_policy(config_path)
    except ConfigError as exc:
        click.echo(str(exc), err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    resolved_repo = _resolve_repo(repo)
    owner, name = _split_repo(resolved_repo)

    try:
        with GitHubClient(token=_resolve_token(token), owner=owner, repo=name) as client:
            rulesets_cache = prefetch_rulesets(client, config, force=config.strict)
            results = apply_all(client, config, rulesets_cache=rulesets_cache)
            if config.strict:
                for deleted_name in prune_rulesets(client, config, rulesets_cache=rulesets_cache):
                    click.echo(f"- removed orphaned ruleset {deleted_name}")
            repo_settings_result = apply_repo_settings(client, config)
    except GitHubAPIError as exc:
        click.echo(str(exc), err=True)
        sys.exit(EXIT_API_ERROR)

    for result in results:
        if result.applied:
            click.echo(f"{result.branch}: applied {len(result.changes)} change(s)")
        else:
            click.echo(f"{result.branch}: no changes needed")

    if repo_settings_result.applied:
        click.echo(f"repo settings: applied {len(repo_settings_result.changes)} change(s)")
    for field_name in repo_settings_result.unavailable:
        click.echo(f"repo settings: {field_name} unavailable on this repository")

    sys.exit(EXIT_OK)
```

- [ ] **Step 25: Run to verify pass**

Run: `pytest tests/test_cli.py -v -k repo_settings`
Expected: `PASS`

- [ ] **Step 26: Run the full suite**

Run: `pytest -v`
Expected: `PASS`, no skips.

- [ ] **Step 27: Run ruff and mypy**

Run: `ruff check .` and `mypy src`
Expected: both clean.

- [ ] **Step 28: Commit**

```bash
git add src/repo_policy/models.py src/repo_policy/github_client.py \
  src/repo_policy/policies/repo_settings.py src/repo_policy/repo_settings.py \
  src/repo_policy/render.py src/repo_policy/cli.py \
  tests/fixtures/policy_repo_settings.yml \
  tests/test_models.py tests/test_github_client.py tests/test_policies_repo_settings.py \
  tests/test_repo_settings.py tests/test_render.py tests/test_cli.py
git commit -m "feat: add repo_settings section — delete_branch_on_merge, allow_update_branch

First slice of repo-wide (non-branch) settings management, closing part
of the gap against a sibling tool's fixed baseline. Establishes the full
new architecture end-to-end: RepoSettingsPolicy schema, pure diff
translation (policies/repo_settings.py), orchestration
(repo_settings.py), rendering, and CLI wiring in audit/plan/apply.
diff_security_and_analysis/diff_toggle ship as pure, fully-tested
functions here but aren't wired into orchestration yet -- that happens
in the task that also adds the matching live GitHubClient method, so no
commit in this series ever reports a policy.yml field as drifted that
apply can't actually fix. Zero API calls when policy.yml has no
repo_settings section, matching every existing adopter's current
behavior exactly."
```

---

### Task 2: `vulnerability_alerts`

**Files:**
- Modify: `src/repo_policy/github_client.py` (`get_vulnerability_alerts`, `enable_vulnerability_alerts`)
- Modify: `src/repo_policy/repo_settings.py` (`plan_repo_settings`, `apply_repo_settings`)
- Modify: `src/repo_policy/render.py` (`_REPO_SETTINGS_LABELS`)
- Test: `tests/test_github_client.py`, `tests/test_repo_settings.py`, `tests/test_render.py`

**Interfaces:**
- Consumes: `diff_toggle` from Task 1 (`policies/repo_settings.py`) — first orchestration use.
- Produces: `GitHubClient.get_vulnerability_alerts() -> bool`, `GitHubClient.enable_vulnerability_alerts() -> None`.

- [ ] **Step 1: Write the failing client tests in `tests/test_github_client.py`**

```python
@respx.mock
def test_get_vulnerability_alerts_enabled(client):
    respx.get("https://api.github.com/repos/acme/widgets/vulnerability-alerts").mock(
        return_value=httpx.Response(204)
    )
    assert client.get_vulnerability_alerts() is True


@respx.mock
def test_get_vulnerability_alerts_disabled(client):
    respx.get("https://api.github.com/repos/acme/widgets/vulnerability-alerts").mock(
        return_value=httpx.Response(404)
    )
    assert client.get_vulnerability_alerts() is False


@respx.mock
def test_enable_vulnerability_alerts(client):
    route = respx.put("https://api.github.com/repos/acme/widgets/vulnerability-alerts").mock(
        return_value=httpx.Response(204)
    )
    client.enable_vulnerability_alerts()
    assert route.called
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_github_client.py -v -k vulnerability_alerts`
Expected: `FAIL`

- [ ] **Step 3: Add the two methods to `src/repo_policy/github_client.py`**

```python
    def get_vulnerability_alerts(self) -> bool:
        response = self._request(
            "GET", f"/repos/{self.owner}/{self.repo}/vulnerability-alerts", allow_404=True
        )
        return response is not None

    def enable_vulnerability_alerts(self) -> None:
        self._request("PUT", f"/repos/{self.owner}/{self.repo}/vulnerability-alerts")
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_github_client.py -v -k vulnerability_alerts`
Expected: `PASS`

- [ ] **Step 5: Write the failing orchestration tests in `tests/test_repo_settings.py`**

```python
def test_plan_repo_settings_detects_vulnerability_alerts_drift():
    client = MagicMock()
    client.get_repo.return_value = {}
    client.get_vulnerability_alerts.return_value = False
    config = PolicyConfig(version=1, branches={}, repo_settings=RepoSettingsPolicy(vulnerability_alerts=True))
    result = plan_repo_settings(client, config)
    assert len(result.changes) == 1
    assert result.changes[0].field == "vulnerability_alerts"


def test_apply_repo_settings_enables_vulnerability_alerts():
    client = MagicMock()
    client.get_repo.return_value = {}
    client.get_vulnerability_alerts.return_value = False
    config = PolicyConfig(version=1, branches={}, repo_settings=RepoSettingsPolicy(vulnerability_alerts=True))
    result = apply_repo_settings(client, config)
    assert result.applied is True
    client.enable_vulnerability_alerts.assert_called_once()
```

(Add `from repo_policy.models import RepoSettingsPolicy` to this test file's imports if not already
present from Task 1.)

- [ ] **Step 6: Run to verify failure**

Run: `pytest tests/test_repo_settings.py -v -k vulnerability_alerts`
Expected: `FAIL`

- [ ] **Step 7: Wire `vulnerability_alerts` into `src/repo_policy/repo_settings.py`**

Change the import line to add `diff_toggle`:

```python
from repo_policy.policies.repo_settings import (
    RepoSettingChange,
    diff_flat_settings,
    diff_toggle,
    to_flat_settings_payload,
)
```

In `plan_repo_settings`, after `result.changes.extend(diff_flat_settings(current_repo, desired))`:

```python
    if desired.vulnerability_alerts is not None:
        current = client.get_vulnerability_alerts()
        result.changes.extend(diff_toggle("vulnerability_alerts", current, desired.vulnerability_alerts))
```

In `apply_repo_settings`, after the existing `flat_changes` block, add a `changed_fields` set and
the toggle:

```python
    changed_fields = {c.field for c in result.changes}
    if "vulnerability_alerts" in changed_fields:
        client.enable_vulnerability_alerts()
```

- [ ] **Step 8: Run to verify pass**

Run: `pytest tests/test_repo_settings.py -v -k vulnerability_alerts`
Expected: `PASS`

- [ ] **Step 9: Add the render label**

```python
    "vulnerability_alerts": "Dependabot alerts",
```

- [ ] **Step 10: Run the full suite, ruff, and mypy**

Run: `pytest -v` / `ruff check .` / `mypy src`
Expected: all clean.

- [ ] **Step 11: Commit**

```bash
git add -u
git commit -m "feat: enforce vulnerability_alerts (Dependabot alerts)

Free on every repo. Foundational for the next field in this series
(automated_security_fixes), which GitHub requires this to already be
enabled before it can be turned on."
```

---

### Task 3: `automated_security_fixes`

**Files:**
- Modify: `src/repo_policy/github_client.py` (`get_automated_security_fixes`, `enable_automated_security_fixes`)
- Modify: `src/repo_policy/repo_settings.py`
- Modify: `src/repo_policy/render.py`
- Test: `tests/test_models.py` (the ordering-dependency validator, declared in Task 1 but untested until now), `tests/test_github_client.py`, `tests/test_repo_settings.py`, `tests/test_render.py`

**Interfaces:**
- Consumes: `RepoSettingsPolicy`'s `_automated_security_fixes_requires_vulnerability_alerts`
  validator, already written in Task 1 Step 3.
- Produces: `GitHubClient.get_automated_security_fixes() -> bool`,
  `GitHubClient.enable_automated_security_fixes() -> None`.

- [ ] **Step 1: Write the failing validator tests in `tests/test_models.py`**

```python
def test_repo_settings_rejects_automated_security_fixes_without_vulnerability_alerts():
    with pytest.raises(ValidationError, match="vulnerability_alerts"):
        RepoSettingsPolicy(automated_security_fixes=True)


def test_repo_settings_rejects_automated_security_fixes_with_vulnerability_alerts_false():
    with pytest.raises(ValidationError, match="vulnerability_alerts"):
        RepoSettingsPolicy(automated_security_fixes=True, vulnerability_alerts=False)


def test_repo_settings_allows_automated_security_fixes_with_vulnerability_alerts_true():
    policy = RepoSettingsPolicy(automated_security_fixes=True, vulnerability_alerts=True)
    assert policy.automated_security_fixes is True
```

- [ ] **Step 2: Run to verify these already pass**

Run: `pytest tests/test_models.py -v -k automated_security_fixes`
Expected: `PASS` immediately — the validator was written in Task 1 Step 3 specifically so this
model behavior exists before any code depends on it. (This is the one place in this plan where the
"write failing test first" step doesn't fail — call this out rather than being surprised by it.)

- [ ] **Step 3: Write the failing client tests in `tests/test_github_client.py`**

```python
@respx.mock
def test_get_automated_security_fixes_enabled(client):
    respx.get("https://api.github.com/repos/acme/widgets/automated-security-fixes").mock(
        return_value=httpx.Response(200, json={"enabled": True})
    )
    assert client.get_automated_security_fixes() is True


@respx.mock
def test_get_automated_security_fixes_disabled_via_404(client):
    respx.get("https://api.github.com/repos/acme/widgets/automated-security-fixes").mock(
        return_value=httpx.Response(404)
    )
    assert client.get_automated_security_fixes() is False


@respx.mock
def test_enable_automated_security_fixes(client):
    route = respx.put("https://api.github.com/repos/acme/widgets/automated-security-fixes").mock(
        return_value=httpx.Response(204)
    )
    client.enable_automated_security_fixes()
    assert route.called
```

- [ ] **Step 4: Run to verify failure**

Run: `pytest tests/test_github_client.py -v -k automated_security_fixes`
Expected: `FAIL`

- [ ] **Step 5: Add the two methods to `src/repo_policy/github_client.py`**

```python
    def get_automated_security_fixes(self) -> bool:
        response = self._request(
            "GET", f"/repos/{self.owner}/{self.repo}/automated-security-fixes", allow_404=True
        )
        return response is not None and bool(response.json().get("enabled", False))

    def enable_automated_security_fixes(self) -> None:
        self._request("PUT", f"/repos/{self.owner}/{self.repo}/automated-security-fixes")
```

- [ ] **Step 6: Run to verify pass**

Run: `pytest tests/test_github_client.py -v -k automated_security_fixes`
Expected: `PASS`

- [ ] **Step 7: Write the failing ordering-dependency orchestration test in `tests/test_repo_settings.py`**

```python
def test_apply_repo_settings_enables_alerts_before_security_fixes():
    """Both fields are drifted in the same apply -- vulnerability_alerts must be enabled first,
    since GitHub rejects enabling automated_security_fixes before it."""
    call_order = []
    client = MagicMock()
    client.get_repo.return_value = {}
    client.get_vulnerability_alerts.return_value = False
    client.get_automated_security_fixes.return_value = False
    client.enable_vulnerability_alerts.side_effect = lambda: call_order.append("vulnerability_alerts")
    client.enable_automated_security_fixes.side_effect = lambda: call_order.append("automated_security_fixes")
    config = PolicyConfig(
        version=1, branches={},
        repo_settings=RepoSettingsPolicy(vulnerability_alerts=True, automated_security_fixes=True),
    )
    apply_repo_settings(client, config)
    assert call_order == ["vulnerability_alerts", "automated_security_fixes"]
```

- [ ] **Step 8: Run to verify failure**

Run: `pytest tests/test_repo_settings.py -v -k "enables_alerts_before"`
Expected: `FAIL`

- [ ] **Step 9: Wire `automated_security_fixes` into `src/repo_policy/repo_settings.py`**

In `plan_repo_settings`, after the `vulnerability_alerts` block added in Task 2:

```python
    if desired.automated_security_fixes is not None:
        current = client.get_automated_security_fixes()
        result.changes.extend(diff_toggle("automated_security_fixes", current, desired.automated_security_fixes))
```

In `apply_repo_settings`, after the `vulnerability_alerts` block added in Task 2 (order matters —
this must come strictly after, not before or interleaved):

```python
    # Must run after vulnerability_alerts, above -- GitHub requires Dependabot alerts enabled
    # before Dependabot security updates can be turned on. RepoSettingsPolicy's model validator
    # (models.py) already guarantees automated_security_fixes=True never appears without
    # vulnerability_alerts=True declared, but that only constrains what's *declared* -- this
    # ordering is what makes the two live API calls land in the right sequence.
    if "automated_security_fixes" in changed_fields:
        client.enable_automated_security_fixes()
```

- [ ] **Step 10: Run to verify pass**

Run: `pytest tests/test_repo_settings.py -v -k automated_security_fixes`
Expected: `PASS`

- [ ] **Step 11: Add the render label**

```python
    "automated_security_fixes": "Dependabot security updates",
```

- [ ] **Step 12: Run the full suite, ruff, and mypy**

Run: `pytest -v` / `ruff check .` / `mypy src`
Expected: all clean.

- [ ] **Step 13: Commit**

```bash
git add -u
git commit -m "feat: enforce automated_security_fixes (Dependabot security updates)

Must apply after vulnerability_alerts in the same run -- GitHub rejects
enabling Dependabot security updates before Dependabot alerts. Guarded
two ways: RepoSettingsPolicy's model validator (Task 1) rejects a
policy.yml that declares automated_security_fixes: true without also
declaring vulnerability_alerts: true, at parse time; apply_repo_settings
additionally sequences the two live API calls correctly for the case
where both are changing in the same run."
```

---

### Task 4: `private_vulnerability_reporting`

Introduces the `unavailable` outcome for the first time — not every repo is eligible (e.g.
dependency graph disabled), independent of any license.

**Files:**
- Modify: `src/repo_policy/github_client.py` (`_request` gains `allow_422`; `get_private_vulnerability_reporting`, `enable_private_vulnerability_reporting`)
- Modify: `src/repo_policy/repo_settings.py`
- Modify: `src/repo_policy/render.py`
- Test: `tests/test_github_client.py`, `tests/test_repo_settings.py`, `tests/test_render.py`

**Interfaces:**
- Produces: `GitHubClient._request(..., allow_422: bool = False)` (extended signature, used by
  Task 5 too); `GitHubClient.get_private_vulnerability_reporting() -> bool | None` (`None` =
  unavailable); `GitHubClient.enable_private_vulnerability_reporting() -> bool` (`False` = the
  enable itself hit 422/unavailable).

- [ ] **Step 1: Write the failing `_request` extension test in `tests/test_github_client.py`**

```python
@respx.mock
def test_request_allow_422_returns_none_on_422(client):
    respx.get("https://api.github.com/repos/acme/widgets/private-vulnerability-reporting").mock(
        return_value=httpx.Response(422, json={"message": "not eligible"})
    )
    response = client._request(
        "GET", "/repos/acme/widgets/private-vulnerability-reporting", allow_422=True
    )
    assert response is None


@respx.mock
def test_request_without_allow_422_raises_on_422(client):
    respx.get("https://api.github.com/repos/acme/widgets/private-vulnerability-reporting").mock(
        return_value=httpx.Response(422, json={"message": "not eligible"})
    )
    with pytest.raises(GitHubAPIError):
        client._request("GET", "/repos/acme/widgets/private-vulnerability-reporting")
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_github_client.py -v -k allow_422`
Expected: `FAIL` — `_request` has no `allow_422` parameter.

- [ ] **Step 3: Extend `_request` in `src/repo_policy/github_client.py`**

```python
    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        allow_404: bool = False,
        allow_422: bool = False,
    ) -> httpx.Response | None:
        attempt = 0
        while True:
            response = self._client.request(method, path, json=json, params=params)

            if response.status_code == 404 and allow_404:
                return None
            if response.status_code == 422 and allow_422:
                return None
            if response.status_code < 400:
                return response

            is_rate_limited = response.status_code == 429 or (
                response.status_code == 403 and "rate limit" in response.text.lower()
            )
            is_retryable = is_rate_limited or response.status_code >= 500

            if is_retryable and attempt < self._max_retries:
                time.sleep(self._backoff_seconds * (2**attempt))
                attempt += 1
                continue

            raise GitHubAPIError(
                f"GitHub API error {response.status_code} on {method} {path}: {response.text}",
                status_code=response.status_code,
            )
```

(This is the existing `_request` body with two new lines inserted — the rest is unchanged; every
existing call site keeps working identically since `allow_422` defaults to `False`.)

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_github_client.py -v -k allow_422`
Expected: `PASS`

- [ ] **Step 5: Write the failing `private_vulnerability_reporting` client tests**

```python
@respx.mock
def test_get_private_vulnerability_reporting_enabled(client):
    respx.get("https://api.github.com/repos/acme/widgets/private-vulnerability-reporting").mock(
        return_value=httpx.Response(200, json={"enabled": True})
    )
    assert client.get_private_vulnerability_reporting() is True


@respx.mock
def test_get_private_vulnerability_reporting_unavailable_via_404(client):
    respx.get("https://api.github.com/repos/acme/widgets/private-vulnerability-reporting").mock(
        return_value=httpx.Response(404)
    )
    assert client.get_private_vulnerability_reporting() is None


@respx.mock
def test_get_private_vulnerability_reporting_unavailable_via_422(client):
    respx.get("https://api.github.com/repos/acme/widgets/private-vulnerability-reporting").mock(
        return_value=httpx.Response(422, json={"message": "not eligible"})
    )
    assert client.get_private_vulnerability_reporting() is None


@respx.mock
def test_enable_private_vulnerability_reporting_succeeds(client):
    respx.put("https://api.github.com/repos/acme/widgets/private-vulnerability-reporting").mock(
        return_value=httpx.Response(204)
    )
    assert client.enable_private_vulnerability_reporting() is True


@respx.mock
def test_enable_private_vulnerability_reporting_unavailable_via_422(client):
    respx.put("https://api.github.com/repos/acme/widgets/private-vulnerability-reporting").mock(
        return_value=httpx.Response(422, json={"message": "not eligible"})
    )
    assert client.enable_private_vulnerability_reporting() is False
```

- [ ] **Step 6: Run to verify failure**

Run: `pytest tests/test_github_client.py -v -k private_vulnerability_reporting`
Expected: `FAIL`

- [ ] **Step 7: Add the two methods to `src/repo_policy/github_client.py`**

```python
    def get_private_vulnerability_reporting(self) -> bool | None:
        """None means unavailable (404 or 422) -- not every repo is eligible."""
        response = self._request(
            "GET", f"/repos/{self.owner}/{self.repo}/private-vulnerability-reporting",
            allow_404=True, allow_422=True,
        )
        return bool(response.json().get("enabled", True)) if response is not None else None

    def enable_private_vulnerability_reporting(self) -> bool:
        """Returns False (meaning unavailable) on 422; True on success."""
        response = self._request(
            "PUT", f"/repos/{self.owner}/{self.repo}/private-vulnerability-reporting", allow_422=True
        )
        return response is not None
```

- [ ] **Step 8: Run to verify pass**

Run: `pytest tests/test_github_client.py -v -k private_vulnerability_reporting`
Expected: `PASS`

- [ ] **Step 9: Write the failing orchestration tests in `tests/test_repo_settings.py`**

```python
def test_plan_repo_settings_records_unavailable_when_pvr_ineligible():
    client = MagicMock()
    client.get_repo.return_value = {}
    client.get_private_vulnerability_reporting.return_value = None
    config = PolicyConfig(version=1, branches={}, repo_settings=RepoSettingsPolicy(private_vulnerability_reporting=True))
    result = plan_repo_settings(client, config)
    assert result.changes == []
    assert result.unavailable == ["private_vulnerability_reporting"]


def test_apply_repo_settings_records_unavailable_when_enable_hits_422():
    client = MagicMock()
    client.get_repo.return_value = {}
    client.get_private_vulnerability_reporting.return_value = False
    client.enable_private_vulnerability_reporting.return_value = False
    config = PolicyConfig(version=1, branches={}, repo_settings=RepoSettingsPolicy(private_vulnerability_reporting=True))
    result = apply_repo_settings(client, config)
    assert "private_vulnerability_reporting" in result.unavailable
```

- [ ] **Step 10: Run to verify failure**

Run: `pytest tests/test_repo_settings.py -v -k private_vulnerability_reporting`
Expected: `FAIL`

- [ ] **Step 11: Wire `private_vulnerability_reporting` into `src/repo_policy/repo_settings.py`**

In `plan_repo_settings`, after the `automated_security_fixes` block from Task 3:

```python
    if desired.private_vulnerability_reporting is not None:
        current = client.get_private_vulnerability_reporting()
        if current is None:
            result.unavailable.append("private_vulnerability_reporting")
        else:
            result.changes.extend(
                diff_toggle("private_vulnerability_reporting", current, desired.private_vulnerability_reporting)
            )
```

In `apply_repo_settings`, after the `automated_security_fixes` block from Task 3:

```python
    if "private_vulnerability_reporting" in changed_fields:
        applied = client.enable_private_vulnerability_reporting()
        if not applied:
            result.unavailable.append("private_vulnerability_reporting")
```

- [ ] **Step 12: Run to verify pass**

Run: `pytest tests/test_repo_settings.py -v -k private_vulnerability_reporting`
Expected: `PASS`

- [ ] **Step 13: Add the render label**

```python
    "private_vulnerability_reporting": "Private vulnerability reporting",
```

- [ ] **Step 14: Confirm `render_repo_settings`'s existing `unavailable` rendering (Task 1 Step 19) already covers this field**

No code change needed — Task 1 already built the `?` line for anything in `result.unavailable`
generically. Add one test confirming it renders this specific field correctly:

```python
def test_render_repo_settings_shows_unavailable():
    result = RepoSettingsResult(unavailable=["private_vulnerability_reporting"])
    output = render_repo_settings("acme/widgets", result)
    assert "? Private vulnerability reporting   unavailable on this repository" in output
```

Run: `pytest tests/test_render.py -v -k unavailable` — expect `PASS` immediately (rendering
infrastructure already exists; this just proves it against a real field for the first time).

- [ ] **Step 15: Run the full suite, ruff, and mypy**

Run: `pytest -v` / `ruff check .` / `mypy src`
Expected: all clean.

- [ ] **Step 16: Commit**

```bash
git add -u
git commit -m "feat: enforce private_vulnerability_reporting

Free on every repo, but not every repo is eligible (e.g. dependency
graph disabled) -- introduces the unavailable outcome, informational and
distinct from drift or an error, first used here."
```

---

### Task 5: `secret_scanning` + `secret_scanning_push_protection`

Highest security value in this series, GHAS-gated. Reuses Task 4's `allow_422`/`unavailable`
pattern. **This is the task that finally wires `diff_security_and_analysis`/
`to_security_and_analysis_payload` (pure functions shipped in Task 1) into orchestration**, since
this is the first task where the matching `GitHubClient.update_security_and_analysis` method also
exists — see this plan's header Amendment.

**Files:**
- Modify: `src/repo_policy/github_client.py` (`update_security_and_analysis`)
- Modify: `src/repo_policy/repo_settings.py` (imports, `plan_repo_settings`, `apply_repo_settings`)
- Modify: `src/repo_policy/render.py`
- Test: `tests/test_github_client.py`, `tests/test_repo_settings.py`, `tests/test_render.py`

**Interfaces:**
- Consumes: `diff_security_and_analysis`/`to_security_and_analysis_payload` from Task 1
  (`policies/repo_settings.py`) — first orchestration use.
- Produces: `GitHubClient.update_security_and_analysis(payload: dict) -> dict | None` (`None` =
  unavailable).

- [ ] **Step 1: Write the failing client tests**

```python
@respx.mock
def test_update_security_and_analysis_succeeds(client):
    respx.patch("https://api.github.com/repos/acme/widgets").mock(
        return_value=httpx.Response(200, json={"security_and_analysis": {"secret_scanning": {"status": "enabled"}}})
    )
    data = client.update_security_and_analysis({"secret_scanning": {"status": "enabled"}})
    assert data is not None


@respx.mock
def test_update_security_and_analysis_unavailable_via_422(client):
    respx.patch("https://api.github.com/repos/acme/widgets").mock(
        return_value=httpx.Response(422, json={"message": "GHAS not enabled"})
    )
    assert client.update_security_and_analysis({"secret_scanning": {"status": "enabled"}}) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_github_client.py -v -k security_and_analysis`
Expected: `FAIL`

- [ ] **Step 3: Add `update_security_and_analysis` to `src/repo_policy/github_client.py`**

```python
    def update_security_and_analysis(self, payload: dict) -> dict | None:
        """Returns None when GitHub Advanced Security isn't licensed on this repo (422) -- an
        expected, non-error outcome, not every repo has it. Any other failure still raises."""
        response = self._request(
            "PATCH", f"/repos/{self.owner}/{self.repo}",
            json={"security_and_analysis": payload}, allow_422=True,
        )
        return response.json() if response is not None else None
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_github_client.py -v -k security_and_analysis`
Expected: `PASS`

- [ ] **Step 5: Write the failing orchestration tests in `tests/test_repo_settings.py`**

```python
def test_plan_repo_settings_detects_secret_scanning_drift():
    client = MagicMock()
    client.get_repo.return_value = {"security_and_analysis": {"secret_scanning": {"status": "disabled"}}}
    config = PolicyConfig(version=1, branches={}, repo_settings=RepoSettingsPolicy(secret_scanning=True))
    result = plan_repo_settings(client, config)
    assert len(result.changes) == 1
    assert result.changes[0].field == "secret_scanning"


def test_apply_repo_settings_records_unavailable_when_ghas_not_licensed():
    client = MagicMock()
    client.get_repo.return_value = {"security_and_analysis": {"secret_scanning": {"status": "disabled"}}}
    client.update_security_and_analysis.return_value = None
    config = PolicyConfig(version=1, branches={}, repo_settings=RepoSettingsPolicy(secret_scanning=True))
    result = apply_repo_settings(client, config)
    assert result.unavailable == ["secret_scanning"]


def test_apply_repo_settings_records_both_fields_unavailable_together():
    client = MagicMock()
    client.get_repo.return_value = {
        "security_and_analysis": {
            "secret_scanning": {"status": "disabled"},
            "secret_scanning_push_protection": {"status": "disabled"},
        }
    }
    client.update_security_and_analysis.return_value = None
    config = PolicyConfig(
        version=1, branches={},
        repo_settings=RepoSettingsPolicy(secret_scanning=True, secret_scanning_push_protection=True),
    )
    result = apply_repo_settings(client, config)
    assert sorted(result.unavailable) == ["secret_scanning", "secret_scanning_push_protection"]


def test_apply_repo_settings_applies_secret_scanning_when_ghas_licensed():
    client = MagicMock()
    client.get_repo.return_value = {"security_and_analysis": {"secret_scanning": {"status": "disabled"}}}
    client.update_security_and_analysis.return_value = {"security_and_analysis": {"secret_scanning": {"status": "enabled"}}}
    config = PolicyConfig(version=1, branches={}, repo_settings=RepoSettingsPolicy(secret_scanning=True))
    result = apply_repo_settings(client, config)
    assert result.applied is True
    assert result.unavailable == []
    client.update_security_and_analysis.assert_called_once_with({"secret_scanning": {"status": "enabled"}})
```

- [ ] **Step 6: Run to verify failure**

Run: `pytest tests/test_repo_settings.py -v -k "secret_scanning or ghas"`
Expected: `FAIL` — `plan_repo_settings` doesn't check `security_and_analysis` yet, and
`apply_repo_settings` doesn't call `client.update_security_and_analysis` yet (that method itself
didn't even exist before Step 3 of this task).

- [ ] **Step 7: Wire `diff_security_and_analysis`/`to_security_and_analysis_payload` into `src/repo_policy/repo_settings.py`**

Update the import block to bring in the two remaining pure functions from Task 1:

```python
from repo_policy.policies.repo_settings import (
    RepoSettingChange,
    diff_flat_settings,
    diff_security_and_analysis,
    diff_toggle,
    to_flat_settings_payload,
    to_security_and_analysis_payload,
)
```

In `plan_repo_settings`, after `result.changes.extend(diff_flat_settings(current_repo, desired))`
(this can go immediately after that line, before or after the toggle-field blocks Tasks 2-4 added —
order among these doesn't matter since they're independent):

```python
    result.changes.extend(diff_security_and_analysis(current_repo, desired))
```

In `apply_repo_settings`, after the existing `flat_changes` block:

```python
    security_changes = [
        c for c in result.changes if c.field in ("secret_scanning", "secret_scanning_push_protection")
    ]
    if security_changes:
        outcome = client.update_security_and_analysis(to_security_and_analysis_payload(security_changes))
        if outcome is None:
            result.unavailable.extend(sorted({c.field for c in security_changes}))
```

- [ ] **Step 8: Run to verify pass**

Run: `pytest tests/test_repo_settings.py -v -k "secret_scanning or ghas"`
Expected: `PASS`

- [ ] **Step 9: Add the render labels**

```python
    "secret_scanning": "Secret scanning",
    "secret_scanning_push_protection": "Secret scanning push protection",
```

- [ ] **Step 10: Run the full suite, ruff, and mypy**

Run: `pytest -v` / `ruff check .` / `mypy src`
Expected: all clean.

- [ ] **Step 11: Commit**

```bash
git add -u
git commit -m "feat: enforce secret_scanning and secret_scanning_push_protection

Highest security value in this series, GHAS-gated -- 422 means no
GitHub Advanced Security license, surfaced as unavailable (Task 4's
pattern), not an error. Wires diff_security_and_analysis/
to_security_and_analysis_payload (pure functions shipped in Task 1) into
plan_repo_settings/apply_repo_settings for the first time, now that
GitHubClient.update_security_and_analysis exists to make them usable
end-to-end. Completes the 7-field repo_settings series."
```

---

### Task 6: Documentation

**Files:**
- Modify: `ARCHITECTURE.md`
- Modify: `ROADMAP.md`

- [ ] **Step 1: Add a Domain Model entry to `ARCHITECTURE.md`**

After the existing `BranchPolicy`/`PullRequestPolicy`/`StatusChecksPolicy` bullets, add:

```markdown
- **`RepoSettingsPolicy`** — an optional, repo-wide (not per-branch) section: `delete_branch_on_merge`,
  `allow_update_branch`, `vulnerability_alerts`, `automated_security_fixes`,
  `private_vulnerability_reporting`, `secret_scanning`, `secret_scanning_push_protection`. `None`
  on any field means "not declared" (same modeling choice as `BranchPolicy`), and the whole section
  can be `None` (not declared at all) — the most common case for every `policy.yml` written before
  this feature existed, which makes zero repo-settings API calls. Unlike branch-level fields,
  `repo_settings` does **not** participate in `strict` mode — there's no universal "permissive
  baseline" that would be safe to auto-apply for e.g. `delete_branch_on_merge`, so this section is
  managed-scope only, always. `automated_security_fixes: true` requires `vulnerability_alerts: true`
  to also be declared — enforced by a model validator, since GitHub rejects enabling Dependabot
  security updates before Dependabot alerts.
```

Add a Container/Component View entry for the two new files, next to the existing `policies/` list:

```markdown
├── repo_settings.py            orchestration for the repo-wide repo_settings section:
│                                plan_repo_settings / apply_repo_settings
└── policies/
    ...
    └── repo_settings.py        RepoSettingsPolicy <-> 3 different GitHub endpoint shapes
                                 (flat PATCH, nested security_and_analysis PATCH, 3 independent
                                 GET/PUT toggle endpoints)
```

Add a new subsection after "Apply Safety Model":

```markdown
## Repo-Level Settings: the `unavailable` Outcome

Two of the seven `repo_settings` fields can come back `unavailable` rather than `ok`/drifted:
`secret_scanning`/`secret_scanning_push_protection` (422 = no GitHub Advanced Security license) and
`private_vulnerability_reporting` (404 or 422 = repo not eligible, e.g. dependency graph disabled).
`unavailable` is informational, not a compliance failure — it never sets `audit`/`plan`'s drift exit
code, and `apply` reports it as a plain message rather than an error. `GitHubClient._request` gained
an `allow_422` parameter (mirroring the existing `allow_404`) specifically to make this
distinguishable from a genuine API error.
```

- [ ] **Step 2: Update `ROADMAP.md`**

Remove this bullet from "Later (directional, unscheduled)":

```markdown
- Repo-level security & settings management: secret scanning + push protection, Dependabot alerts
  and security-fix automation, private vulnerability reporting, `delete_branch_on_merge`,
  `allow_update_branch`. Out of scope today — repo-policy only manages branch protection/rulesets,
  not repo-wide settings.
```

Add a row to the "Now" table:

```markdown
| Model repo-level settings (7 fields: Dependabot, secret scanning, repo settings) | Second half of closing the gap against a sibling tool's fixed baseline — branch-protection fields (Phase 1) already shipped | shipped | TBD |
```

- [ ] **Step 3: Run the full suite one more time**

Run: `pytest -v` / `ruff check .` / `mypy src`
Expected: all clean.

- [ ] **Step 4: Commit**

```bash
git add ARCHITECTURE.md ROADMAP.md
git commit -m "docs: document the repo_settings section and its unavailable outcome

ARCHITECTURE.md's Domain Model, Container/Component View, and a new
Repo-Level Settings subsection; ROADMAP.md's Later section updated to
mark this phase shipped."
```

---

## Self-Review

**Spec coverage:** All 7 fields (`delete_branch_on_merge`, `allow_update_branch`,
`vulnerability_alerts`, `automated_security_fixes`, `private_vulnerability_reporting`,
`secret_scanning`, `secret_scanning_push_protection`) have a task. The verified API contract table
is fully consumed: every endpoint in it is called from exactly one `github_client.py` method
written in this plan. The ordering dependency (`automated_security_fixes` after
`vulnerability_alerts`) is enforced two ways (parse-time validator + apply-time sequencing), per the
Global Constraints. The "never combine the two PATCH bodies" constraint is respected — Task 1's flat
settings and Task 5's security-and-analysis changes are always sent as two separate
`client.update_repo_settings`/`client.update_security_and_analysis` calls, never merged.

**Placeholder scan:** No TODO/TBD/"add appropriate" language in any code step. Task 3 Step 2's "this
test already passes" is a deliberate, explained exception to the usual failing-first flow, not a
placeholder.

**Type consistency:** `RepoSettingChange`, `RepoSettingsResult`, `plan_repo_settings`,
`apply_repo_settings`, and every `GitHubClient` method signature are defined once (Task 1 or the
task that introduces that specific field) and reused with matching names/types in every later task.

**Amendment record (post Task-1-execution):** the original draft of this plan wired
`diff_security_and_analysis` into `plan_repo_settings` as part of Task 1, before
`GitHubClient.update_security_and_analysis` existed — `mypy` caught the resulting `attr-defined`
error immediately, and closer inspection showed it would have been a real product bug even without
mypy's help (a field `plan` reports as drifted that `apply` silently can never fix). Corrected: all
mock/fixture examples throughout this document now reflect this codebase's real testing
conventions (`respx.mock` + `client` fixture for `github_client.py`; `unittest.mock.MagicMock()` for
orchestration; `@patch("repo_policy.cli.GitHubClient")` + `CliRunner` for CLI), confirmed by reading
`tests/test_github_client.py`, `tests/test_apply.py`, and `tests/test_cli.py` before writing Task 1 —
the original draft's `respx_mock`/`mock_get_repo`-style illustrative fixture names have been
replaced with the real ones throughout.
