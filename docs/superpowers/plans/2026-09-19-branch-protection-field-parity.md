# Branch-Protection Field Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Model six branch-protection fields that repo-policy currently either doesn't represent at
all, or explicitly reads-through/preserves from live GitHub state instead of enforcing:
`enforce_admins`, `required_conversation_resolution`, `lock_branch`, `allow_fork_syncing`,
`dismiss_stale_reviews`, `require_last_push_approval`.

**Architecture:** Two different shapes, chosen per field based on where it lives in GitHub's API
and whether GitHub Rulesets can represent it at all:

1. **`dismiss_stale_reviews` / `require_last_push_approval`** become new fields on
   `PullRequestPolicy` (nested inside the existing `pull_requests` `BranchPolicy` field). Both
   GitHub backends already have a slot for them (`required_pull_request_reviews` sub-object /
   `pull_request` ruleset rule parameters) — this converts an existing read-through into a modeled,
   enforced value, fully symmetric across both backends, using exactly the pattern `approvals` and
   `code_owner_review` already use.
2. **`enforce_admins` / `required_conversation_resolution` / `lock_branch` /
   `allow_fork_syncing`** become four new top-level `BranchPolicy` fields (same shape as
   `linear_history`/`allow_force_push`/`allow_deletion`). None of the four have a GitHub Rulesets
   equivalent — `enforce_admins`/`lock_branch`/`allow_fork_syncing` have no ruleset concept at all,
   and `required_conversation_resolution`'s nearest ruleset cousin
   (`required_review_thread_resolution`) only exists as a sub-parameter of the `pull_request` rule,
   which doesn't always exist (e.g. when `pull_requests.required` is false) — so it can't be
   represented independently. Rather than build that partial, sometimes-silently-unenforceable
   mapping, all four fields are **branch_protection-only**: a new Pydantic model validator on
   `BranchPolicy` rejects policy.yml files that set any of them to a *non-permissive* value on a
   branch with `enforcement: ruleset`, at `validate`/parse time — fail loud, never silently drop a
   declared rule. The validator specifically allows the permissive (no-op) value through, not just
   `None`: `BranchPolicy` is also used internally to represent live GitHub state (see
   `ARCHITECTURE.md`'s Domain Model section), and `rulesets.from_api()` must be able to construct
   `BranchPolicy(enforcement="ruleset", enforce_admins=False, ...)` — a concrete, non-`None` value —
   for its "current state" objects without tripping the same validator a human's policy.yml goes
   through. `rulesets.from_api()` hardcodes all four to their permissive constant so
   `resolve_desired()`/`diff()` never report phantom drift for a ruleset-enforced branch, in either
   managed-scope or strict mode.

**Tech Stack:** Python 3.10+, Pydantic v2 (model validators), pytest (existing test suite
conventions — see below).

**Spec:** No separate spec doc; this plan is scoped directly from a real gap analysis against a
sibling internal tool (`/home/amit/repos/McCainFoods/sre-observability-gates/repo_security/`, not
part of this repo) that already enforces these six fields via the classic branch-protection API,
cross-checked against repo-policy's own `ARCHITECTURE.md`, `ROADMAP.md`, and existing test suite to
confirm exactly which fields are genuinely unmodeled today and why.

## Global Constraints

- Every new field ships with the project's stated testing convention: TDD (failing test first),
  happy-path + expected-failure coverage per `AGENTS.md`. This repo's own `docs/test-strategy.md`
  additionally requires the cross-backend **parity test** (`tests/test_policies_parity.py`) stay
  green for every field in `diff._FIELDS` — this is not optional; it exists specifically because a
  past bug shipped through exactly this gap (a field wired into one backend's translator but not
  the other's, invisible to any test that only checked one backend).
- No new GitHub API endpoints are needed. `enforce_admins`, `required_conversation_resolution`,
  `lock_branch`, `allow_fork_syncing` are all top-level fields on the *existing*
  `PUT /branches/{branch}/protection` payload `branch_protection.to_api_payload()` already builds —
  confirmed by reading `github_client.put_branch_protection` and the current `to_api_payload`
  function, which already sends this exact endpoint.
- No schema version bump (`policy.yml`'s `version: 1` stays `1`) — these are additive optional
  fields, not a breaking change to the existing schema.
- Every commit message follows Conventional Commits (`feat: ...`) — `python-semantic-release`
  reads commit history to cut the next release automatically (see `docs/ci-cd.md`); do not hand-edit
  `CHANGELOG.md`.
- Follow existing polarity convention exactly: a field is normal-polarity (`False`/unset = no
  restriction) unless GitHub's own default for that field is `true`, in which case it joins
  `diff._INVERTED_FIELDS` (`True`/unset = no restriction) — the same reasoning already applied to
  `allow_force_push`/`allow_deletion`. `allow_fork_syncing`'s GitHub default is `true`, so it is
  inverted; the other three new top-level fields default `false` on GitHub, so they are not.

---

## File Structure

| File | Responsibility after this plan |
|---|---|
| `src/repo_policy/models.py` | `PullRequestPolicy` gains 2 fields; `BranchPolicy` gains 4 fields + one new model validator rejecting the 4 ruleset-unsupported fields when `enforcement: ruleset` |
| `src/repo_policy/diff.py` | `_FIELDS`, `_SCHEMA_DEFAULTS`, `_INVERTED_FIELDS` extended with the 4 new top-level fields |
| `src/repo_policy/policies/pull_requests.py` | `to_branch_protection` drops its now-unused `current` read-through param and always emits the 2 new fields from the policy; `from_branch_protection`, `to_ruleset_rule`, `from_ruleset_rule` read/write them |
| `src/repo_policy/policies/branch_protection.py` | `from_api`/`to_api_payload` read/write the 4 new top-level fields; call site drops the now-removed `current` arg to `pull_requests.to_branch_protection` |
| `src/repo_policy/policies/rulesets.py` | `from_api` hardcodes the 4 ruleset-unsupported fields to their permissive constant (comment explains why) |
| `src/repo_policy/render.py` | `_LABELS` gains 4 entries |
| `tests/test_models.py` | new validator tests |
| `tests/test_policies_pull_requests.py` | 2 obsolete tests rewritten, new tests for the 2 new fields on both backends |
| `tests/test_policies_branch_protection.py` | 1 obsolete test rewritten (stale "preserved" assertions removed), new tests for the 4 new fields |
| `tests/test_policies_rulesets.py` | new tests asserting the 4 hardcoded permissive constants |
| `tests/test_policies_parity.py` | `RESTRICTIVE_VALUES` extended; new `RULESET_FIELDS` subset (excludes the 4 ruleset-unsupported fields, with a comment referencing the validator) |
| `tests/test_render.py` | new label-rendering assertions |
| `ARCHITECTURE.md` | Domain Model section updated: field count/list, "doesn't model" bullet narrowed to just `restrictions` and status-check `strict` |
| `ROADMAP.md` | the two "Later" bullets this plan closes are removed/marked shipped |

---

### Task 1: `PullRequestPolicy.dismiss_stale_reviews` + `require_last_push_approval`

**Files:**
- Modify: `src/repo_policy/models.py` (`PullRequestPolicy` class)
- Modify: `src/repo_policy/policies/pull_requests.py` (all 4 functions)
- Modify: `src/repo_policy/policies/branch_protection.py:51-53` (call site — drop the now-removed `current` arg)
- Modify: `tests/test_policies_pull_requests.py` (rewrite 2 obsolete tests, add 4 new ones)
- Modify: `tests/test_policies_branch_protection.py` (rewrite `test_to_api_payload_preserves_unmodeled_nested_review_and_check_fields`)
- Modify: `tests/test_policies_parity.py` (`RESTRICTIVE_VALUES["pull_requests"]`)

**Interfaces:**
- Consumes: nothing new from other tasks (this task is self-contained and goes first).
- Produces: `PullRequestPolicy(required, approvals, code_owner_review, dismiss_stale_reviews, require_last_push_approval)` — Task 2+ don't touch `PullRequestPolicy`, but the parity test infrastructure this task doesn't yet need (`RULESET_FIELDS`) is introduced in Task 2.

- [ ] **Step 1: Write the failing tests in `tests/test_policies_pull_requests.py`**

Replace the two now-obsolete tests (`test_to_branch_protection_defaults_unmodeled_fields_false_when_no_current_state` and `test_to_branch_protection_preserves_unmodeled_fields_from_current_state` — both describe behavior this task removes) and add coverage for the two new fields on both backends:

```python
def test_to_branch_protection_includes_dismiss_stale_reviews_and_last_push_approval():
    policy = PullRequestPolicy(
        required=True, approvals=2, code_owner_review=True,
        dismiss_stale_reviews=True, require_last_push_approval=True,
    )
    payload = pull_requests.to_branch_protection(policy)
    assert payload["dismiss_stale_reviews"] is True
    assert payload["require_last_push_approval"] is True


def test_to_branch_protection_defaults_new_fields_false():
    policy = PullRequestPolicy(required=True, approvals=2, code_owner_review=True)
    payload = pull_requests.to_branch_protection(policy)
    assert payload["dismiss_stale_reviews"] is False
    assert payload["require_last_push_approval"] is False


def test_from_branch_protection_reads_dismiss_stale_reviews_and_last_push_approval():
    data = {
        "required_approving_review_count": 3,
        "require_code_owner_reviews": True,
        "dismiss_stale_reviews": True,
        "require_last_push_approval": True,
    }
    result = pull_requests.from_branch_protection(data)
    assert result.dismiss_stale_reviews is True
    assert result.require_last_push_approval is True


def test_ruleset_rule_round_trips_dismiss_stale_reviews_and_last_push_approval():
    policy = PullRequestPolicy(
        required=True, approvals=1, code_owner_review=False,
        dismiss_stale_reviews=True, require_last_push_approval=True,
    )
    rule = pull_requests.to_ruleset_rule(policy)
    assert rule["parameters"]["dismiss_stale_reviews_on_push"] is True
    assert rule["parameters"]["require_last_push_approval"] is True
    result = pull_requests.from_ruleset_rule(rule)
    assert result.dismiss_stale_reviews is True
    assert result.require_last_push_approval is True
```

Delete the two obsolete tests entirely (do not leave them alongside the new ones — they assert the
opposite of the new intended behavior).

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest tests/test_policies_pull_requests.py -v`
Expected: `FAIL` — `PullRequestPolicy` has no fields `dismiss_stale_reviews`/`require_last_push_approval` yet, and `to_branch_protection` still reads `current`.

- [ ] **Step 3: Add the two fields to `PullRequestPolicy` in `src/repo_policy/models.py`**

```python
class PullRequestPolicy(BaseModel):
    required: bool = True
    approvals: int = 1
    code_owner_review: bool = False
    dismiss_stale_reviews: bool = False
    require_last_push_approval: bool = False
```

- [ ] **Step 4: Rewrite `src/repo_policy/policies/pull_requests.py`**

```python
from __future__ import annotations

from repo_policy.models import PullRequestPolicy


def to_branch_protection(policy: PullRequestPolicy) -> dict | None:
    """dismiss_stale_reviews/require_last_push_approval are modeled directly on PullRequestPolicy
    (previously read through from current state — see docs/superpowers/plans/
    2026-09-19-branch-protection-field-parity.md for why that changed)."""
    if not policy.required:
        return None
    return {
        "required_approving_review_count": policy.approvals,
        "require_code_owner_reviews": policy.code_owner_review,
        "dismiss_stale_reviews": policy.dismiss_stale_reviews,
        "require_last_push_approval": policy.require_last_push_approval,
    }


def from_branch_protection(data: dict | None) -> PullRequestPolicy:
    if data is None:
        return PullRequestPolicy(
            required=False, approvals=0, code_owner_review=False,
            dismiss_stale_reviews=False, require_last_push_approval=False,
        )
    return PullRequestPolicy(
        required=True,
        approvals=data.get("required_approving_review_count", 0),
        code_owner_review=data.get("require_code_owner_reviews", False),
        dismiss_stale_reviews=data.get("dismiss_stale_reviews", False),
        require_last_push_approval=data.get("require_last_push_approval", False),
    )


def to_ruleset_rule(policy: PullRequestPolicy) -> dict | None:
    if not policy.required:
        return None
    return {
        "type": "pull_request",
        "parameters": {
            "required_approving_review_count": policy.approvals,
            "require_code_owner_review": policy.code_owner_review,
            "require_last_push_approval": policy.require_last_push_approval,
            "dismiss_stale_reviews_on_push": policy.dismiss_stale_reviews,
            # required_conversation_resolution has no independent ruleset representation and is
            # rejected for enforcement: ruleset by BranchPolicy's model validator (models.py) —
            # always False here, not a placeholder. See this plan's Architecture section.
            "required_review_thread_resolution": False,
        },
    }


def from_ruleset_rule(rule: dict | None) -> PullRequestPolicy:
    if rule is None:
        return PullRequestPolicy(
            required=False, approvals=0, code_owner_review=False,
            dismiss_stale_reviews=False, require_last_push_approval=False,
        )
    params = rule["parameters"]
    return PullRequestPolicy(
        required=True,
        approvals=params.get("required_approving_review_count", 0),
        code_owner_review=params.get("require_code_owner_review", False),
        dismiss_stale_reviews=params.get("dismiss_stale_reviews_on_push", False),
        require_last_push_approval=params.get("require_last_push_approval", False),
    )
```

- [ ] **Step 5: Update the call site in `src/repo_policy/policies/branch_protection.py`**

Change line 51-53 from:

```python
        "required_pull_request_reviews": pull_requests.to_branch_protection(
            resolved.pull_requests, current_raw.get("required_pull_request_reviews")
        ),
```

to:

```python
        "required_pull_request_reviews": pull_requests.to_branch_protection(resolved.pull_requests),
```

- [ ] **Step 6: Run tests, expect PASS**

Run: `pytest tests/test_policies_pull_requests.py -v`
Expected: `PASS`

- [ ] **Step 7: Fix the now-broken test in `tests/test_policies_branch_protection.py`**

`test_to_api_payload_preserves_unmodeled_nested_review_and_check_fields` currently asserts
`dismiss_stale_reviews`/`require_last_push_approval` get preserved from `current_raw` — that's no
longer true, they're modeled now. Replace the whole test:

```python
def test_to_api_payload_preserves_unmodeled_status_check_strict_field():
    """Regression test: a targeted change to one declared field (allow_force_push) must not
    silently reset the status-check 'strict' (require branches up to date) setting — the one
    remaining nested field repo-policy doesn't model but a human may have set manually on GitHub.
    (dismiss_stale_reviews/require_last_push_approval used to be covered by this same test, but
    became modeled fields — see tests/test_policies_pull_requests.py instead.)"""
    current_raw = {
        "required_pull_request_reviews": {
            "required_approving_review_count": 2,
            "require_code_owner_reviews": True,
        },
        "required_status_checks": {"contexts": ["build"], "checks": [], "strict": True},
    }
    resolved = BranchPolicy(
        pull_requests=PullRequestPolicy(required=True, approvals=2, code_owner_review=True),
        status_checks=StatusChecksPolicy(required=["build"]),
        linear_history=False,
        allow_force_push=False,  # the only field actually changing
        allow_deletion=True,
        enforce_admins=False,
        required_conversation_resolution=False,
        lock_branch=False,
        allow_fork_syncing=True,
    )
    payload = branch_protection.to_api_payload(resolved, current_raw=current_raw)
    assert payload["required_status_checks"]["strict"] is True
```

(This references `enforce_admins`/`required_conversation_resolution`/`lock_branch`/
`allow_fork_syncing` on `resolved` — they don't exist on `BranchPolicy` yet, so this test will fail
to construct until Task 2-5 land. That's expected and fine: this exact test file gets touched again
in Task 2, where those keyword arguments start resolving. For now, run only
`tests/test_policies_pull_requests.py` in Step 6/8; the full suite isn't green again until Task 5.)

- [ ] **Step 8: Update `tests/test_policies_parity.py`**

In `RESTRICTIVE_VALUES`, change:

```python
    "pull_requests": PullRequestPolicy(required=True, approvals=2, code_owner_review=True),
```

to:

```python
    "pull_requests": PullRequestPolicy(
        required=True, approvals=2, code_owner_review=True,
        dismiss_stale_reviews=True, require_last_push_approval=True,
    ),
```

- [ ] **Step 9: Run the pull_requests-focused suite**

Run: `pytest tests/test_policies_pull_requests.py tests/test_policies_parity.py -v`
Expected: `test_policies_pull_requests.py` fully PASS. `test_policies_parity.py` PASS (the
`pull_requests` field parametrize case for both backends already passed before this task and still
does — `PERMISSIVE`/`RESTRICTIVE_VALUES` don't reference the not-yet-existing top-level fields).

- [ ] **Step 10: Commit**

```bash
git add src/repo_policy/models.py src/repo_policy/policies/pull_requests.py \
  src/repo_policy/policies/branch_protection.py tests/test_policies_pull_requests.py \
  tests/test_policies_parity.py
git commit -m "feat: model dismiss_stale_reviews and require_last_push_approval

Previously read through from live GitHub state and never enforced. Both
GitHub backends (classic branch protection's required_pull_request_reviews,
and the ruleset pull_request rule's parameters) already had a slot for
these -- converts them from unmodeled/preserved to declared/enforced,
following the same pattern approvals and code_owner_review already use."
```

(Note: `tests/test_policies_branch_protection.py` is intentionally not staged yet — it's mid-edit
and won't compile clean until Task 2. It'll be committed as part of Task 2's commit.)

---

### Task 2: `enforce_admins` + the ruleset-unsupported-fields model validator

**Files:**
- Modify: `src/repo_policy/models.py` (`BranchPolicy` — add `enforce_admins` field + new model validator)
- Modify: `src/repo_policy/diff.py` (`_FIELDS`, `_SCHEMA_DEFAULTS`)
- Modify: `src/repo_policy/policies/branch_protection.py` (`from_api`, `to_api_payload`)
- Modify: `src/repo_policy/policies/rulesets.py` (`from_api` — hardcode `enforce_admins=False`)
- Modify: `src/repo_policy/render.py` (`_LABELS`)
- Modify: `tests/test_models.py` (validator tests)
- Modify: `tests/test_policies_branch_protection.py` (finish Task 1's pending edit + new `enforce_admins` coverage; also fixes `test_to_api_payload_preserves_unmodeled_current_fields`, which currently treats `enforce_admins` as unmodeled)
- Modify: `tests/test_policies_rulesets.py` (assert hardcoded constant)
- Modify: `tests/test_policies_parity.py` (`RESTRICTIVE_VALUES` entry + new `RULESET_FIELDS` subset)
- Modify: `tests/test_render.py` (label assertion)

**Interfaces:**
- Consumes: `PullRequestPolicy` from Task 1 (unchanged interface, just imported).
- Produces: `BranchPolicy.enforce_admins: bool | None`; the model validator
  `_reject_ruleset_unsupported_fields` and its backing tuple `_RULESET_UNSUPPORTED_FIELDS` — Tasks
  3-5 extend this same tuple, don't redefine it.

- [ ] **Step 1: Write the failing validator tests in `tests/test_models.py`**

```python
def test_branch_policy_rejects_enforce_admins_under_ruleset():
    with pytest.raises(ValidationError, match="enforce_admins"):
        BranchPolicy(enforcement="ruleset", enforce_admins=True)


def test_branch_policy_allows_enforce_admins_under_branch_protection():
    policy = BranchPolicy(enforcement="branch_protection", enforce_admins=True)
    assert policy.enforce_admins is True


def test_branch_policy_allows_ruleset_enforcement_when_enforce_admins_unset():
    policy = BranchPolicy(enforcement="ruleset")
    assert policy.enforce_admins is None
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_models.py -v -k enforce_admins`
Expected: `FAIL` — `BranchPolicy` has no `enforce_admins` field yet.

- [ ] **Step 3: Add the field and validator to `src/repo_policy/models.py`**

Add the import and the field, then the validator, to the existing `BranchPolicy` class:

```python
from pydantic import BaseModel, Field, field_validator, model_validator

# ... (PullRequestPolicy, StatusChecksPolicy unchanged)

# field name -> its permissive (no-op) value under enforcement: ruleset. rulesets.from_api()
# constructs internal "current state" BranchPolicy objects with these exact values for each field
# below (never None) — the validator below must let that through unrejected, so it only rejects a
# *non-permissive* (actually-restrictive) value, not merely a non-None one. A human writing
# `enforce_admins: false` under `enforcement: ruleset` is a harmless no-op declaration and is
# allowed; `enforce_admins: true` is a real restriction with no ruleset equivalent and is rejected.
_RULESET_UNSUPPORTED_FIELDS: dict[str, bool] = {"enforce_admins": False}


class BranchPolicy(BaseModel):
    enforcement: Literal["branch_protection", "ruleset"] = "branch_protection"
    strict: bool | None = None
    pull_requests: PullRequestPolicy | None = None
    status_checks: StatusChecksPolicy | None = None
    signed_commits: bool | None = None
    linear_history: bool | None = None
    allow_force_push: bool | None = None
    allow_deletion: bool | None = None
    enforce_admins: bool | None = None

    @model_validator(mode="after")
    def _reject_ruleset_unsupported_fields(self) -> "BranchPolicy":
        if self.enforcement != "ruleset":
            return self
        set_fields = [
            name for name, permissive in _RULESET_UNSUPPORTED_FIELDS.items()
            if getattr(self, name) not in (None, permissive)
        ]
        if set_fields:
            raise ValueError(
                f"{', '.join(set_fields)} not supported under enforcement: ruleset "
                "(no GitHub Rulesets equivalent) -- use enforcement: branch_protection, "
                "or remove these fields"
            )
        return self
```

**Note (found during execution, not anticipated when this plan was written):** an earlier draft of
this validator rejected any non-`None` value unconditionally. That breaks `rulesets.from_api()`,
which must construct `BranchPolicy(enforcement="ruleset", enforce_admins=False, ...)` — a concrete
value, not `None` — for its internal "current state" representation. The dict-based, permissive-
value-aware check above is the corrected version; use it, not a plain tuple membership check.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_models.py -v -k enforce_admins`
Expected: `PASS`

- [ ] **Step 4b: Fix the same phantom-drift gap `docs/test-strategy.md` warns about, in `tests/test_diff.py`**

`tests/test_diff.py`'s hand-built `PERMISSIVE` `BranchPolicy` fixture doesn't set `enforce_admins`
explicitly, so it defaults to `None` — but every real `from_api()` call now returns a concrete
`False`, never `None`, for this field. Left unfixed, `test_strict_mode_reports_no_drift_for_an_already_compliant_permissive_branch`
fails: strict mode resolves the unset field to the schema default (`False`), diffs it against the
fixture's `None`, and reports a permanent phantom `add` change — exactly the bug class that test
exists to catch. Add `enforce_admins=False` to that fixture:

```python
PERMISSIVE = BranchPolicy(
    pull_requests=PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
    status_checks=None,
    signed_commits=False,
    linear_history=False,
    allow_force_push=True,
    allow_deletion=True,
    enforce_admins=False,
)
```

Run: `pytest tests/test_diff.py -v`
Expected: `PASS`. (Tasks 3-5 each add one more field to this same fixture — the same phantom-drift
failure will otherwise recur at every task boundary.)

- [ ] **Step 5: Add `enforce_admins` to `diff.py`**

In `src/repo_policy/diff.py`, change `_FIELDS` and `_SCHEMA_DEFAULTS`:

```python
_FIELDS = (
    "pull_requests",
    "status_checks",
    "signed_commits",
    "linear_history",
    "allow_force_push",
    "allow_deletion",
    "enforce_admins",
)

_SCHEMA_DEFAULTS: dict[str, Any] = {
    "pull_requests": PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
    "status_checks": None,
    "signed_commits": False,
    "linear_history": False,
    "allow_force_push": True,
    "allow_deletion": True,
    "enforce_admins": False,
}
```

- [ ] **Step 6: Wire `enforce_admins` into `src/repo_policy/policies/branch_protection.py`**

In `from_api`, add `enforce_admins=False` to the `data is None` branch and
`enforce_admins=_unwrap(data.get("enforce_admins"), False)` to the populated branch. In
`to_api_payload`, replace the read-through line:

```python
        "enforce_admins": _unwrap(current_raw.get("enforce_admins"), False),
```

with:

```python
        "enforce_admins": bool(resolved.enforce_admins),
```

- [ ] **Step 7: Wire the hardcoded constant into `src/repo_policy/policies/rulesets.py`**

In `from_api`, add `enforce_admins=False` to both the `data is None` branch and the populated
branch's `BranchPolicy(...)` call, with this comment directly above the populated branch's return:

```python
    # enforce_admins has no GitHub Rulesets equivalent and is rejected for enforcement: ruleset by
    # BranchPolicy's model validator (models.py) -- hardcoded here so resolve_desired()/diff()
    # always report zero drift for it on a ruleset-enforced branch, in every mode.
```

- [ ] **Step 8: Add the render label**

In `src/repo_policy/render.py`, add to `_LABELS`:

```python
    "enforce_admins": "Admin enforcement",
```

- [ ] **Step 9: Finish `tests/test_policies_branch_protection.py`**

The `test_to_api_payload_preserves_unmodeled_status_check_strict_field` test added in Task 1 Step 7
now compiles (its `resolved=BranchPolicy(..., enforce_admins=False, ...)` call references a real
field, but `required_conversation_resolution`/`lock_branch`/`allow_fork_syncing` still don't exist
yet — temporarily drop those three kwargs from that one test's `BranchPolicy(...)` call so it
compiles now; Task 5 adds them back once all four fields exist).

Also fix `test_to_api_payload_preserves_unmodeled_current_fields`, which currently asserts
`enforce_admins` is preserved from `current_raw` — that's no longer true. Replace it:

```python
def test_to_api_payload_preserves_restrictions_from_current_state():
    """restrictions is the one PUT-required field the v1 schema still doesn't model."""
    current_raw = {"restrictions": {"users": ["octocat"], "teams": []}}
    resolved = BranchPolicy(
        pull_requests=PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
        linear_history=False,
        allow_force_push=True,
        allow_deletion=True,
        enforce_admins=False,
    )
    payload = branch_protection.to_api_payload(resolved, current_raw=current_raw)
    assert payload["restrictions"] == {"users": ["octocat"], "teams": []}
```

Add one new test for the now-enforced field:

```python
def test_to_api_payload_writes_enforce_admins_from_resolved_policy():
    resolved = BranchPolicy(
        pull_requests=PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
        linear_history=False,
        allow_force_push=True,
        allow_deletion=True,
        enforce_admins=True,
    )
    payload = branch_protection.to_api_payload(resolved, current_raw={"enforce_admins": {"enabled": False}})
    assert payload["enforce_admins"] is True  # resolved wins, current_raw is ignored for this field now
```

Also update `test_from_api_reads_wrapped_booleans` and `test_from_api_none_means_fully_permissive`
in the same file to assert `result.enforce_admins is True` / `is False` respectively, adding
`"enforce_admins": {"enabled": True}` to that test's input `data` dict.

- [ ] **Step 10: Add coverage in `tests/test_policies_rulesets.py`**

```python
def test_from_api_hardcodes_enforce_admins_false():
    assert rulesets.from_api(None).enforce_admins is False
    assert rulesets.from_api({"rules": []}).enforce_admins is False
```

- [ ] **Step 11: Update `tests/test_policies_parity.py`**

Add to `RESTRICTIVE_VALUES`:

```python
    "enforce_admins": True,
```

Add the new subset and repoint the ruleset-side parametrize, replacing:

```python
@pytest.mark.parametrize("field", _FIELDS)
def test_field_is_represented_by_ruleset_backend(field):
```

with:

```python
# enforce_admins/required_conversation_resolution/lock_branch/allow_fork_syncing have no GitHub
# Rulesets equivalent -- BranchPolicy's model validator (models.py) rejects setting them under
# enforcement: ruleset, so the ruleset backend never needs to represent them (see rulesets.from_api,
# which hardcodes each to its permissive constant instead of reading it).
RULESET_UNSUPPORTED_FIELDS = {
    "enforce_admins", "required_conversation_resolution", "lock_branch", "allow_fork_syncing",
}
RULESET_FIELDS = [f for f in _FIELDS if f not in RULESET_UNSUPPORTED_FIELDS]


@pytest.mark.parametrize("field", RULESET_FIELDS)
def test_field_is_represented_by_ruleset_backend(field):
```

(`RULESET_UNSUPPORTED_FIELDS` references `required_conversation_resolution`/`lock_branch`/
`allow_fork_syncing`, which don't exist as `BranchPolicy` fields until Tasks 3-5 — that's fine, it's
just a set of strings, not attribute access; nothing fails to import.)

- [ ] **Step 12: Add coverage in `tests/test_render.py`**

```python
def test_render_plan_shows_enforce_admins_label():
    changes = [Change(field="enforce_admins", current_value=False, desired_value=True, action="add")]
    output = render_plan("acme/widgets", "main", changes)
    assert "+ Admin enforcement" in output
```

- [ ] **Step 13: Run the full suite**

Run: `pytest -v`
Expected: `PASS` (every file touched so far is now internally consistent — Task 1's temporarily
broken test is fixed by this task's Step 9).

- [ ] **Step 14: Commit**

```bash
git add src/repo_policy/models.py src/repo_policy/diff.py \
  src/repo_policy/policies/branch_protection.py src/repo_policy/policies/rulesets.py \
  src/repo_policy/render.py tests/test_models.py tests/test_diff.py \
  tests/test_policies_branch_protection.py tests/test_policies_rulesets.py \
  tests/test_policies_parity.py tests/test_render.py
git commit -m "feat: model enforce_admins, branch_protection-only

Highest-impact of the branch-protection fields the v1 schema doesn't
model: without it, a repo admin can bypass every other declared rule at
will. No GitHub Rulesets equivalent exists (would require bypass_actors
role-ID configuration, out of scope here), so this is branch_protection
enforcement only -- a new BranchPolicy model validator rejects setting it
under enforcement: ruleset at policy.yml parse time, and rulesets.from_api
hardcodes it to its permissive constant so no ruleset-enforced branch ever
shows phantom drift for a field it structurally cannot represent."
```

---

### Task 3: `required_conversation_resolution`

**Files:** same five source files as Task 2's Steps 5-8, plus `tests/test_policies_branch_protection.py`, `tests/test_policies_rulesets.py`, `tests/test_policies_parity.py`, `tests/test_render.py`, `tests/test_models.py`.

**Interfaces:**
- Consumes: `_RULESET_UNSUPPORTED_FIELDS` from Task 2 (models.py) — extend it, don't redefine it. `RULESET_UNSUPPORTED_FIELDS` set from Task 2 (test_policies_parity.py) — extend it too.
- Produces: `BranchPolicy.required_conversation_resolution: bool | None`.

- [ ] **Step 1: Write the failing tests in `tests/test_models.py`**

```python
def test_branch_policy_rejects_required_conversation_resolution_under_ruleset():
    with pytest.raises(ValidationError, match="required_conversation_resolution"):
        BranchPolicy(enforcement="ruleset", required_conversation_resolution=True)


def test_branch_policy_allows_required_conversation_resolution_under_branch_protection():
    policy = BranchPolicy(enforcement="branch_protection", required_conversation_resolution=True)
    assert policy.required_conversation_resolution is True
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_models.py -v -k required_conversation_resolution`
Expected: `FAIL`

- [ ] **Step 3: Add the field to `BranchPolicy` and extend the validator tuple in `src/repo_policy/models.py`**

```python
_RULESET_UNSUPPORTED_FIELDS: dict[str, bool] = {
    "enforce_admins": False, "required_conversation_resolution": False,
}
```

Add `required_conversation_resolution: bool | None = None` to `BranchPolicy`, directly after
`enforce_admins`.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_models.py -v -k required_conversation_resolution`
Expected: `PASS`

- [ ] **Step 4b: Extend `tests/test_diff.py`'s `PERMISSIVE` fixture**

Same phantom-drift gap as Task 2 Step 4b, one field further. Add `required_conversation_resolution=False`
to `PERMISSIVE`'s `BranchPolicy(...)` call in `tests/test_diff.py`.

Run: `pytest tests/test_diff.py -v`
Expected: `PASS`

- [ ] **Step 5: Add to `diff.py`**

Append `"required_conversation_resolution"` to `_FIELDS`, and
`"required_conversation_resolution": False` to `_SCHEMA_DEFAULTS`.

- [ ] **Step 6: Wire into `src/repo_policy/policies/branch_protection.py`**

`from_api`: add `required_conversation_resolution=False` (None-data branch) and
`required_conversation_resolution=_unwrap(data.get("required_conversation_resolution"), False)`
(populated branch). `to_api_payload`: add
`"required_conversation_resolution": bool(resolved.required_conversation_resolution),` to the
returned dict.

- [ ] **Step 7: Wire the hardcoded constant into `src/repo_policy/policies/rulesets.py`**

Add `required_conversation_resolution=False` to both branches of `from_api`.

- [ ] **Step 8: Add the render label**

```python
    "required_conversation_resolution": "Conversation resolution",
```

- [ ] **Step 9: Restore the full kwargs in `tests/test_policies_branch_protection.py`**

`test_to_api_payload_preserves_unmodeled_status_check_strict_field` (from Task 1/2) had
`required_conversation_resolution`/`lock_branch`/`allow_fork_syncing` temporarily dropped from its
`BranchPolicy(...)` call — add `required_conversation_resolution=False` back in now.

Add a new dedicated test:

```python
def test_to_api_payload_writes_required_conversation_resolution():
    resolved = BranchPolicy(
        pull_requests=PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
        linear_history=False,
        allow_force_push=True,
        allow_deletion=True,
        enforce_admins=False,
        required_conversation_resolution=True,
    )
    payload = branch_protection.to_api_payload(resolved, current_raw=None)
    assert payload["required_conversation_resolution"] is True
```

- [ ] **Step 10: Add coverage in `tests/test_policies_rulesets.py`**

```python
def test_from_api_hardcodes_required_conversation_resolution_false():
    assert rulesets.from_api(None).required_conversation_resolution is False
    assert rulesets.from_api({"rules": []}).required_conversation_resolution is False
```

- [ ] **Step 11: Update `tests/test_policies_parity.py`**

Add `"required_conversation_resolution": True` to `RESTRICTIVE_VALUES`, and add
`"required_conversation_resolution"` into the existing `RULESET_UNSUPPORTED_FIELDS` set from
Task 2 (it's already listed there per Task 2 Step 11 — this step is just confirming/keeping it, no
new edit needed if Task 2 already wrote the full four-item set; if you wrote Task 2's set as
`{"enforce_admins"}` only, extend it now to include `"required_conversation_resolution"`).

- [ ] **Step 12: Add coverage in `tests/test_render.py`**

```python
def test_render_plan_shows_conversation_resolution_label():
    changes = [Change(field="required_conversation_resolution", current_value=False,
                       desired_value=True, action="add")]
    output = render_plan("acme/widgets", "main", changes)
    assert "+ Conversation resolution" in output
```

- [ ] **Step 13: Run the full suite, expect PASS**

Run: `pytest -v`

- [ ] **Step 14: Commit**

```bash
git add -u
git commit -m "feat: model required_conversation_resolution, branch_protection-only

Same shape as enforce_admins: GitHub's nearest ruleset equivalent
(required_review_thread_resolution) only exists as a pull_request rule
parameter, which doesn't always exist (pull_requests.required can be
false) -- rather than build a mapping that's sometimes silently
unenforceable, this stays branch_protection-only, guarded by the same
model validator enforce_admins added."
```

---

### Task 4: `lock_branch`

**Files:** same shape as Task 3.

**Interfaces:**
- Consumes: `_RULESET_UNSUPPORTED_FIELDS` (models.py) and `RULESET_UNSUPPORTED_FIELDS` (test_policies_parity.py) — extend both.
- Produces: `BranchPolicy.lock_branch: bool | None`.

- [ ] **Step 1: Write the failing tests in `tests/test_models.py`**

```python
def test_branch_policy_rejects_lock_branch_under_ruleset():
    with pytest.raises(ValidationError, match="lock_branch"):
        BranchPolicy(enforcement="ruleset", lock_branch=True)


def test_branch_policy_allows_lock_branch_under_branch_protection():
    policy = BranchPolicy(enforcement="branch_protection", lock_branch=True)
    assert policy.lock_branch is True
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_models.py -v -k lock_branch`
Expected: `FAIL`

- [ ] **Step 3: Add field + extend validator tuple in `src/repo_policy/models.py`**

```python
_RULESET_UNSUPPORTED_FIELDS: dict[str, bool] = {
    "enforce_admins": False, "required_conversation_resolution": False, "lock_branch": False,
}
```

Add `lock_branch: bool | None = None` to `BranchPolicy`.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_models.py -v -k lock_branch`
Expected: `PASS`

- [ ] **Step 4b: Extend `tests/test_diff.py`'s `PERMISSIVE` fixture**

Add `lock_branch=False` to `PERMISSIVE`'s `BranchPolicy(...)` call in `tests/test_diff.py`.

Run: `pytest tests/test_diff.py -v`
Expected: `PASS`

- [ ] **Step 5: Add to `diff.py`**

Append `"lock_branch"` to `_FIELDS`, and `"lock_branch": False` to `_SCHEMA_DEFAULTS`.

- [ ] **Step 6: Wire into `src/repo_policy/policies/branch_protection.py`**

`from_api`: add `lock_branch=False` (None-data branch) and
`lock_branch=_unwrap(data.get("lock_branch"), False)` (populated branch). `to_api_payload`: add
`"lock_branch": bool(resolved.lock_branch),`.

- [ ] **Step 7: Wire the hardcoded constant into `src/repo_policy/policies/rulesets.py`**

Add `lock_branch=False` to both branches of `from_api`.

- [ ] **Step 8: Add the render label**

```python
    "lock_branch": "Branch lock",
```

- [ ] **Step 9: Restore `lock_branch=False` in the two `tests/test_policies_branch_protection.py` tests that still need it**

`test_to_api_payload_preserves_unmodeled_status_check_strict_field` and any other `BranchPolicy(...)` construction added in Tasks 2-3 that's missing this kwarg — add `lock_branch=False`.

Add a dedicated test:

```python
def test_to_api_payload_writes_lock_branch():
    resolved = BranchPolicy(
        pull_requests=PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
        linear_history=False,
        allow_force_push=True,
        allow_deletion=True,
        enforce_admins=False,
        required_conversation_resolution=False,
        lock_branch=True,
    )
    payload = branch_protection.to_api_payload(resolved, current_raw=None)
    assert payload["lock_branch"] is True
```

- [ ] **Step 10: Add coverage in `tests/test_policies_rulesets.py`**

```python
def test_from_api_hardcodes_lock_branch_false():
    assert rulesets.from_api(None).lock_branch is False
    assert rulesets.from_api({"rules": []}).lock_branch is False
```

- [ ] **Step 11: Update `tests/test_policies_parity.py`**

Add `"lock_branch": True` to `RESTRICTIVE_VALUES`; extend `RULESET_UNSUPPORTED_FIELDS` to include
`"lock_branch"`.

- [ ] **Step 12: Add coverage in `tests/test_render.py`**

```python
def test_render_plan_shows_lock_branch_label():
    changes = [Change(field="lock_branch", current_value=False, desired_value=True, action="add")]
    output = render_plan("acme/widgets", "main", changes)
    assert "+ Branch lock" in output
```

- [ ] **Step 13: Run the full suite, expect PASS**

Run: `pytest -v`

- [ ] **Step 14: Commit**

```bash
git add -u
git commit -m "feat: model lock_branch, branch_protection-only

Makes the branch fully read-only when true. No ruleset rule type exists
for this at all -- branch_protection-only, guarded by the same
ruleset-unsupported-fields validator as enforce_admins and
required_conversation_resolution."
```

---

### Task 5: `allow_fork_syncing` (inverted polarity)

**Files:** same shape as Task 4, plus `src/repo_policy/diff.py`'s `_INVERTED_FIELDS`.

**Interfaces:**
- Consumes: `_RULESET_UNSUPPORTED_FIELDS` (models.py) and `RULESET_UNSUPPORTED_FIELDS` (test_policies_parity.py) — extend both, final four-item state.
- Produces: `BranchPolicy.allow_fork_syncing: bool | None` — the last new field this plan adds.

- [ ] **Step 1: Write the failing tests in `tests/test_models.py`**

```python
def test_branch_policy_rejects_allow_fork_syncing_under_ruleset():
    with pytest.raises(ValidationError, match="allow_fork_syncing"):
        BranchPolicy(enforcement="ruleset", allow_fork_syncing=False)


def test_branch_policy_allows_allow_fork_syncing_under_branch_protection():
    policy = BranchPolicy(enforcement="branch_protection", allow_fork_syncing=False)
    assert policy.allow_fork_syncing is False
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_models.py -v -k allow_fork_syncing`
Expected: `FAIL`

- [ ] **Step 3: Add field + finalize the validator tuple in `src/repo_policy/models.py`**

```python
_RULESET_UNSUPPORTED_FIELDS: dict[str, bool] = {
    "enforce_admins": False, "required_conversation_resolution": False, "lock_branch": False,
    "allow_fork_syncing": True,  # inverted polarity: True is the permissive value here
}
```

Add `allow_fork_syncing: bool | None = None` to `BranchPolicy`.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_models.py -v -k allow_fork_syncing`
Expected: `PASS`

- [ ] **Step 4b: Extend `tests/test_diff.py`'s `PERMISSIVE` fixture**

Add `allow_fork_syncing=True` to `PERMISSIVE`'s `BranchPolicy(...)` call in `tests/test_diff.py`
(the permissive value here is `True`, not `False` — inverted polarity, same as `allow_force_push`/
`allow_deletion`).

Run: `pytest tests/test_diff.py -v`
Expected: `PASS`

- [ ] **Step 5: Add to `diff.py`, including the inverted-polarity registration**

Append `"allow_fork_syncing"` to `_FIELDS`, `"allow_fork_syncing": True` to `_SCHEMA_DEFAULTS`
(GitHub's own default is `true` — this is the permissive value, same reasoning as
`allow_force_push`/`allow_deletion`), and add it to `_INVERTED_FIELDS`:

```python
_INVERTED_FIELDS = {"allow_force_push", "allow_deletion", "allow_fork_syncing"}
```

- [ ] **Step 6: Write a targeted diff-polarity test in `tests/test_diff.py`**

```python
def test_allow_fork_syncing_inverted_polarity_add_vs_remove():
    """Mirrors the existing allow_force_push/allow_deletion polarity tests: False is the
    restrictive value here (True is GitHub's own permissive default), same as those two."""
    current = PERMISSIVE.model_copy(update={"allow_fork_syncing": False})
    desired = PERMISSIVE.model_copy(update={"allow_fork_syncing": True})
    changes = diff(desired, current)
    assert len(changes) == 1
    assert changes[0].action == "remove"  # restriction is being lifted
```

(`PERMISSIVE`'s `allow_fork_syncing=True` was already added in Step 4b — this step only adds the
new targeted test above.)

- [ ] **Step 7: Run to verify pass**

Run: `pytest tests/test_diff.py -v`
Expected: `PASS`

- [ ] **Step 8: Wire into `src/repo_policy/policies/branch_protection.py`**

`from_api`: add `allow_fork_syncing=True` (None-data branch — GitHub's permissive default) and
`allow_fork_syncing=_unwrap(data.get("allow_fork_syncing"), True)` (populated branch). `to_api_payload`:
add `"allow_fork_syncing": bool(resolved.allow_fork_syncing),`.

- [ ] **Step 9: Wire the hardcoded constant into `src/repo_policy/policies/rulesets.py`**

Add `allow_fork_syncing=True` to both branches of `from_api`.

- [ ] **Step 10: Add the render label**

```python
    "allow_fork_syncing": "Fork syncing",
```

- [ ] **Step 11: Finalize `tests/test_policies_branch_protection.py`**

Every `BranchPolicy(...)` construction added across Tasks 1-5 in this file now needs all four new
top-level kwargs present for consistency (even though most default sensibly to `None`→resolved
values via `resolve_desired` in real usage, these tests construct already-`resolved` policies
directly, so pydantic's own field defaults apply — `enforce_admins`/`required_conversation_resolution`/
`lock_branch` default `None`, `allow_fork_syncing` defaults `None` too, so omitting them is
harmless here; no further code change needed, just confirm the suite is green in Step 13).

Add a dedicated test:

```python
def test_to_api_payload_writes_allow_fork_syncing():
    resolved = BranchPolicy(
        pull_requests=PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
        linear_history=False,
        allow_force_push=True,
        allow_deletion=True,
        allow_fork_syncing=False,
    )
    payload = branch_protection.to_api_payload(resolved, current_raw=None)
    assert payload["allow_fork_syncing"] is False
```

- [ ] **Step 12: Add coverage in `tests/test_policies_rulesets.py`**

```python
def test_from_api_hardcodes_allow_fork_syncing_true():
    assert rulesets.from_api(None).allow_fork_syncing is True
    assert rulesets.from_api({"rules": []}).allow_fork_syncing is True
```

- [ ] **Step 13: Finalize `tests/test_policies_parity.py`**

Add `"allow_fork_syncing": False` to `RESTRICTIVE_VALUES` (the restrictive/non-permissive value,
given inverted polarity). Confirm `RULESET_UNSUPPORTED_FIELDS` now reads:

```python
RULESET_UNSUPPORTED_FIELDS = {
    "enforce_admins", "required_conversation_resolution", "lock_branch", "allow_fork_syncing",
}
```

- [ ] **Step 14: Add coverage in `tests/test_render.py`**

```python
def test_render_plan_shows_fork_syncing_label():
    changes = [Change(field="allow_fork_syncing", current_value=True, desired_value=False, action="add")]
    output = render_plan("acme/widgets", "main", changes)
    assert "+ Fork syncing" in output
```

- [ ] **Step 15: Run the entire suite**

Run: `pytest -v`
Expected: `PASS`, all tests, no skips.

- [ ] **Step 16: Commit**

```bash
git add -u
git commit -m "feat: model allow_fork_syncing, branch_protection-only

Completes the four branch_protection-only fields (with enforce_admins,
required_conversation_resolution, lock_branch). Inverted polarity like
allow_force_push/allow_deletion: GitHub's own default is true (syncing
allowed), so true/unset is the permissive value here, not false."
```

---

### Task 6: Documentation

**Files:**
- Modify: `ARCHITECTURE.md`
- Modify: `ROADMAP.md`

**Interfaces:**
- Consumes: nothing code-level; this task is pure documentation reflecting Tasks 1-5's shipped state.
- Produces: nothing consumed elsewhere.

- [ ] **Step 1: Update `ARCHITECTURE.md`'s Domain Model section**

Replace this sentence (currently lines 55-59):

```markdown
- **`BranchPolicy`** — one branch's desired state: `enforcement` (`branch_protection` | `ruleset`,
  default `branch_protection`), an optional per-branch `strict` override, and six *optional*
  policy fields (`pull_requests`, `status_checks`, `signed_commits`, `linear_history`,
  `allow_force_push`, `allow_deletion`). `None` on any of these six means "not declared" — this is
  the single most important modeling choice in the codebase (see `docs/adrs/0003-*`).
```

with:

```markdown
- **`BranchPolicy`** — one branch's desired state: `enforcement` (`branch_protection` | `ruleset`,
  default `branch_protection`), an optional per-branch `strict` override, and ten *optional*
  policy fields (`pull_requests`, `status_checks`, `signed_commits`, `linear_history`,
  `allow_force_push`, `allow_deletion`, `enforce_admins`, `required_conversation_resolution`,
  `lock_branch`, `allow_fork_syncing`). `None` on any of these ten means "not declared" — this is
  the single most important modeling choice in the codebase (see `docs/adrs/0003-*`). The last
  four have no GitHub Rulesets equivalent (`required_conversation_resolution`'s nearest cousin,
  `required_review_thread_resolution`, only exists as a `pull_request` rule parameter, which
  doesn't always exist) — a model validator on `BranchPolicy` rejects declaring any of them on a
  branch with `enforcement: ruleset` at `validate` time, and `PullRequestPolicy` additionally
  carries `dismiss_stale_reviews`/`require_last_push_approval`, which *are* fully cross-backend.
```

- [ ] **Step 2: Update the "Managed-scope" bullet under Apply Safety Model**

Replace (currently lines 116-122):

```markdown
- **Managed-scope (default):** `apply` never touches a branch absent from `policy.yml`. Within a
  declared branch, only the fields present in `policy.yml` are enforced; everything else — for
  `branch_protection`, this includes GitHub settings the v1 schema doesn't model at all
  (`enforce_admins`, `restrictions`, and the nested `dismiss_stale_reviews` /
  `require_last_push_approval` / status-check `strict` fields) — is read from current state and
  passed straight through, never reset. For `ruleset`, the tool only ever creates/reads/updates a
  ruleset named `repo-policy:<branch>`; it never inspects or modifies any other ruleset.
```

with:

```markdown
- **Managed-scope (default):** `apply` never touches a branch absent from `policy.yml`. Within a
  declared branch, only the fields present in `policy.yml` are enforced; everything else — for
  `branch_protection`, this now only includes `restrictions` and the status-check `strict` field,
  the two GitHub settings the v1 schema still doesn't model at all (`enforce_admins` and the nested
  `dismiss_stale_reviews`/`require_last_push_approval` became modeled, enforced fields — see the
  Domain Model section above) — is read from current state and passed straight through, never
  reset. For `ruleset`, the tool only ever creates/reads/updates a ruleset named
  `repo-policy:<branch>`; it never inspects or modifies any other ruleset.
```

- [ ] **Step 3: Update `ROADMAP.md`**

Remove the two bullets this plan closes from "Later (directional, unscheduled)":

```markdown
- Additional branch-protection fields repo-policy doesn't model yet: `enforce_admins`,
  `dismiss_stale_reviews`, `require_last_push_approval`, `required_conversation_resolution`,
  `lock_branch`, `allow_fork_syncing`. Currently read through from whatever's already set on the
  branch rather than enforced — see `to_api_payload()` / `pull_requests.to_branch_protection()`.
```

Add a row to the "Now" table instead (adjust `Target` to the next release once known — leave `TBD`
if this lands before a release is cut):

```markdown
| Model the 6 previously-unenforced branch-protection fields | Closed a real coverage gap against a sibling tool's fixed baseline; `enforce_admins` in particular is the highest-impact single field repo-policy didn't enforce | shipped | TBD |
```

Leave the other "Later" bullet (repo-level security & settings management) untouched — it's still
out of scope, unrelated to this plan.

- [ ] **Step 4: Commit**

```bash
git add ARCHITECTURE.md ROADMAP.md
git commit -m "docs: reflect the 6 newly-modeled branch-protection fields

ARCHITECTURE.md's Domain Model and Apply Safety Model sections, and
ROADMAP.md's Later section, described the pre-this-plan state (fields
read-through/unmodeled). Updates both to match what Tasks 1-5 shipped."
```

---

## Self-Review

**Spec coverage:** All six target fields (`enforce_admins`, `required_conversation_resolution`,
`lock_branch`, `allow_fork_syncing`, `dismiss_stale_reviews`, `require_last_push_approval`) have a
task. Both prior turns' priority ranking (enforce_admins first among the four top-level fields) and
"prefers small increments" are reflected in task ordering and per-field granularity.

**Placeholder scan:** No TODO/TBD/"add appropriate"/"similar to Task N" language in any code step;
every step shows the literal code to write. The one deliberately-partial intermediate state (Task 1
Step 7's test referencing fields that don't exist until Task 2) is explicitly called out as expected
and temporary, with the exact task that resolves it named.

**Type consistency:** `PullRequestPolicy(required, approvals, code_owner_review,
dismiss_stale_reviews, require_last_push_approval)` and `BranchPolicy`'s four new `bool | None`
fields are used with matching names/types across every task that touches them (Tasks 2-5 each
extend, never redefine, `_RULESET_UNSUPPORTED_FIELDS` and `RULESET_UNSUPPORTED_FIELDS`).
