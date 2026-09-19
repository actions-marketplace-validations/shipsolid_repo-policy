# `clear_restrictions` Field Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `clear_restrictions` to `BranchPolicy`, the last field-level gap between repo-policy
and the sibling `repo_security` tool's baseline — GitHub's branch-protection `restrictions` (push
allowlist), which `repo_security` unconditionally resets to `null` on every apply and repo-policy
has never modeled (always pass-through/preserve).

**Architecture:** Reuses the exact `_RULESET_UNSUPPORTED_FIELDS` validator mechanism Phase 1 built
for `enforce_admins`/`required_conversation_resolution`/`lock_branch`/`allow_fork_syncing` (see
`docs/superpowers/plans/2026-09-19-branch-protection-field-parity.md`) — same shape, same
precedent, branch_protection-only since GitHub Rulesets has no equivalent concept. Normal polarity,
not inverted: `True` means "restrictions must be null," which is also GitHub's own out-of-the-box
default, so it doubles correctly as the strict-mode schema default.

**Tech Stack:** Python 3.10+, Pydantic v2 — same stack as Phase 1/2, no new dependencies.

**Spec:** No separate spec doc. Scoped directly in conversation from a concrete question ("how do
we handle the `restrictions` gap") after the Phase 1/2 gap-closing work
(`docs/superpowers/plans/2026-09-19-branch-protection-field-parity.md`,
`docs/superpowers/plans/2026-09-19-repo-level-settings-management.md`, both merged) left this one
field unaddressed. Design cross-checked against those two plans' proven conventions, not re-derived.

## Global Constraints

- Normal polarity: `True` = "restrictions must be null" (also GitHub's own default), `False`/`None`
  (undeclared) = "leave whatever's currently there alone" — today's existing, unchanged behavior
  for every `policy.yml` that doesn't use this field. Do **not** add `clear_restrictions` to
  `diff._INVERTED_FIELDS`.
- Branch_protection-only, guarded by the existing `_RULESET_UNSUPPORTED_FIELDS` validator — no new
  validator mechanism, extend the existing dict.
- Every commit follows Conventional Commits (`feat: ...`); never hand-edit `CHANGELOG.md`.
- TDD throughout: failing test first.
- `pytest`, `ruff check .`, and `mypy src` clean at every task's commit, not just the plan's end —
  Phase 1 and Phase 2 both found real bugs (a `ruff` UP037 violation, a `mypy` attr-defined error)
  by holding this bar at every task, not just the last one.
- Both hand-built `PERMISSIVE` `BranchPolicy` fixtures (`tests/test_diff.py`,
  `tests/test_policies_parity.py`) must get `clear_restrictions=True` added explicitly in the same
  task that adds the field — Phase 1 found this exact gap by omission four separate times (once per
  field) before catching the pattern; get it right the first time here.

---

## File Structure

| File | Change |
|---|---|
| `src/repo_policy/models.py` | `BranchPolicy` gains `clear_restrictions: bool \| None = None`; `_RULESET_UNSUPPORTED_FIELDS` gains one entry |
| `src/repo_policy/diff.py` | `_FIELDS` gains `"clear_restrictions"`; `_SCHEMA_DEFAULTS` gains `"clear_restrictions": True` |
| `src/repo_policy/policies/branch_protection.py` | `from_api` sets `clear_restrictions` from live state; `to_api_payload`'s `restrictions` line and docstring both change |
| `src/repo_policy/policies/rulesets.py` | `from_api` hardcodes `clear_restrictions=True` in both branches |
| `src/repo_policy/render.py` | `_LABELS` gains `"clear_restrictions": "Push restrictions"` |
| `tests/test_models.py` | New validator tests |
| `tests/test_diff.py` | `PERMISSIVE` fixture updated |
| `tests/test_policies_branch_protection.py` | New `from_api`/`to_api_payload` tests |
| `tests/test_policies_rulesets.py` | New hardcoded-constant test |
| `tests/test_policies_parity.py` | `PERMISSIVE`, `RESTRICTIVE_VALUES`, `RULESET_UNSUPPORTED_FIELDS` all updated |
| `tests/test_render.py` | New label test |
| `ARCHITECTURE.md` | Domain Model field count/list corrected; Apply Safety Model bullet corrected; `to_api_payload` docstring correction already covered under the `branch_protection.py` row above, but the *prose* in ARCHITECTURE.md describing it independently also needs the same correction |
| `ROADMAP.md` | One row added to "Now", matching the Phase 1/2 row convention |

---

### Task 1: `clear_restrictions`

**Files:**
- Modify: `src/repo_policy/models.py`
- Modify: `src/repo_policy/diff.py`
- Modify: `src/repo_policy/policies/branch_protection.py`
- Modify: `src/repo_policy/policies/rulesets.py`
- Modify: `src/repo_policy/render.py`
- Test: `tests/test_models.py`, `tests/test_diff.py`, `tests/test_policies_branch_protection.py`, `tests/test_policies_rulesets.py`, `tests/test_policies_parity.py`, `tests/test_render.py`

**Interfaces:**
- Produces: `BranchPolicy.clear_restrictions: bool | None` — no other task in this plan consumes it
  further; Task 2 is docs-only.

- [ ] **Step 1: Write the failing validator tests in `tests/test_models.py`**

```python
def test_branch_policy_rejects_clear_restrictions_under_ruleset():
    with pytest.raises(ValidationError, match="clear_restrictions"):
        BranchPolicy(enforcement="ruleset", clear_restrictions=False)


def test_branch_policy_allows_clear_restrictions_under_branch_protection():
    policy = BranchPolicy(enforcement="branch_protection", clear_restrictions=True)
    assert policy.clear_restrictions is True
```

Note the first test declares `clear_restrictions=False`, not `True` — `False` is the
*non-permissive* value here (the permissive value is `True`), so it's the one the validator must
reject under `enforcement: ruleset`, exactly mirroring how Phase 1's
`test_branch_policy_rejects_allow_fork_syncing_under_ruleset` declared `allow_fork_syncing=False`
for the same reason (that field is also permissive-when-`True`).

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_models.py -v -k clear_restrictions`
Expected: `FAIL` — `BranchPolicy` has no `clear_restrictions` field yet.

- [ ] **Step 3: Add the field and extend the validator dict in `src/repo_policy/models.py`**

Change:

```python
_RULESET_UNSUPPORTED_FIELDS: dict[str, bool] = {
    "enforce_admins": False, "required_conversation_resolution": False, "lock_branch": False,
    "allow_fork_syncing": True,  # inverted polarity: True is the permissive value here
}
```

to:

```python
_RULESET_UNSUPPORTED_FIELDS: dict[str, bool] = {
    "enforce_admins": False, "required_conversation_resolution": False, "lock_branch": False,
    "allow_fork_syncing": True,  # inverted polarity: True is the permissive value here
    "clear_restrictions": True,  # True is the permissive value here too: no restriction in effect
}
```

Add `clear_restrictions: bool | None = None` to `BranchPolicy`, directly after `allow_fork_syncing`:

```python
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
    required_conversation_resolution: bool | None = None
    lock_branch: bool | None = None
    allow_fork_syncing: bool | None = None
    clear_restrictions: bool | None = None
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_models.py -v -k clear_restrictions`
Expected: `PASS`

- [ ] **Step 5: Extend `tests/test_diff.py`'s `PERMISSIVE` fixture**

Add `clear_restrictions=True` to the `BranchPolicy(...)` call:

```python
PERMISSIVE = BranchPolicy(
    pull_requests=PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
    status_checks=None,
    signed_commits=False,
    linear_history=False,
    allow_force_push=True,
    allow_deletion=True,
    enforce_admins=False,
    required_conversation_resolution=False,
    lock_branch=False,
    allow_fork_syncing=True,
    clear_restrictions=True,
)
```

Run: `pytest tests/test_diff.py -v`
Expected: `PASS` (nothing in `diff._FIELDS` includes `clear_restrictions` yet at this point in the
task, so this is a no-op change that just keeps the fixture ready for Step 6 — confirm it's still
green before continuing, not because this step alone could fail).

- [ ] **Step 6: Add `clear_restrictions` to `src/repo_policy/diff.py`**

Change `_FIELDS`:

```python
_FIELDS = (
    "pull_requests",
    "status_checks",
    "signed_commits",
    "linear_history",
    "allow_force_push",
    "allow_deletion",
    "enforce_admins",
    "required_conversation_resolution",
    "lock_branch",
    "allow_fork_syncing",
    "clear_restrictions",
)
```

Change `_SCHEMA_DEFAULTS`:

```python
_SCHEMA_DEFAULTS: dict[str, Any] = {
    "pull_requests": PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
    "status_checks": None,
    "signed_commits": False,
    "linear_history": False,
    "allow_force_push": True,
    "allow_deletion": True,
    "enforce_admins": False,
    "required_conversation_resolution": False,
    "lock_branch": False,
    "allow_fork_syncing": True,
    "clear_restrictions": True,
}
```

Leave `_INVERTED_FIELDS` unchanged — do not add `clear_restrictions` to it.

- [ ] **Step 7: Run `tests/test_diff.py` again to confirm still green**

Run: `pytest tests/test_diff.py -v`
Expected: `PASS`. If `test_strict_mode_reports_no_drift_for_an_already_compliant_permissive_branch`
fails here, it means Step 5's fixture edit was skipped or wrong — go back and fix it before
continuing; this is exactly the phantom-drift bug class Phase 1 hit four times.

- [ ] **Step 8: Write the failing `branch_protection.py` tests in `tests/test_policies_branch_protection.py`**

```python
def test_from_api_none_means_clear_restrictions_true():
    result = branch_protection.from_api(None, signed_commits=False)
    assert result.clear_restrictions is True


def test_from_api_reads_clear_restrictions_true_when_no_live_restriction():
    data = {"restrictions": None}
    result = branch_protection.from_api(data, signed_commits=False)
    assert result.clear_restrictions is True


def test_from_api_reads_clear_restrictions_false_when_live_restriction_exists():
    data = {"restrictions": {"users": ["octocat"], "teams": [], "apps": []}}
    result = branch_protection.from_api(data, signed_commits=False)
    assert result.clear_restrictions is False


def test_to_api_payload_forces_restrictions_null_when_clear_restrictions_true():
    resolved = BranchPolicy(
        pull_requests=PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
        linear_history=False,
        allow_force_push=True,
        allow_deletion=True,
        clear_restrictions=True,
    )
    current_raw = {"restrictions": {"users": ["octocat"], "teams": [], "apps": []}}
    payload = branch_protection.to_api_payload(resolved, current_raw=current_raw)
    assert payload["restrictions"] is None


def test_to_api_payload_preserves_restrictions_when_clear_restrictions_false():
    resolved = BranchPolicy(
        pull_requests=PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
        linear_history=False,
        allow_force_push=True,
        allow_deletion=True,
        clear_restrictions=False,
    )
    current_raw = {"restrictions": {"users": ["octocat"], "teams": [], "apps": []}}
    payload = branch_protection.to_api_payload(resolved, current_raw=current_raw)
    assert payload["restrictions"] == {"users": ["octocat"], "teams": [], "apps": []}
```

Note this file already has `test_to_api_payload_preserves_restrictions_from_current_state` (from
Phase 1) — that test constructs `resolved` **without** setting `clear_restrictions`, so it defaults
to `None`, which is one of the two "leave alone" values; it will keep passing unchanged after this
task's `to_api_payload` edit and needs no modification. Do not delete or rewrite it.

- [ ] **Step 9: Run to verify failure**

Run: `pytest tests/test_policies_branch_protection.py -v -k clear_restrictions`
Expected: `FAIL` — `clear_restrictions` isn't read or written anywhere yet.

- [ ] **Step 10: Wire `clear_restrictions` into `src/repo_policy/policies/branch_protection.py`**

In `from_api`, add `clear_restrictions=True` to the `data is None` branch:

```python
def from_api(data: dict | None, *, signed_commits: bool) -> BranchPolicy:
    if data is None:
        return BranchPolicy(
            enforcement="branch_protection",
            pull_requests=PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
            status_checks=None,
            signed_commits=signed_commits,
            linear_history=False,
            allow_force_push=True,
            allow_deletion=True,
            enforce_admins=False,
            required_conversation_resolution=False,
            lock_branch=False,
            allow_fork_syncing=True,
            clear_restrictions=True,
        )
    return BranchPolicy(
        enforcement="branch_protection",
        pull_requests=pull_requests.from_branch_protection(data.get("required_pull_request_reviews")),
        status_checks=status_checks.from_branch_protection(data.get("required_status_checks")),
        signed_commits=signed_commits,
        linear_history=_unwrap(data.get("required_linear_history"), False),
        allow_force_push=_unwrap(data.get("allow_force_pushes"), True),
        allow_deletion=_unwrap(data.get("allow_deletions"), True),
        enforce_admins=_unwrap(data.get("enforce_admins"), False),
        required_conversation_resolution=_unwrap(data.get("required_conversation_resolution"), False),
        lock_branch=_unwrap(data.get("lock_branch"), False),
        allow_fork_syncing=_unwrap(data.get("allow_fork_syncing"), True),
        clear_restrictions=data.get("restrictions") is None,
    )
```

In `to_api_payload`, change the docstring (the current one is about to become inaccurate — it says
`restrictions` is "the one PUT-required field the v1 schema still doesn't model," which after this
task is no longer true) and the `restrictions` line:

```python
def to_api_payload(resolved: BranchPolicy, current_raw: dict | None) -> dict:
    """`resolved` must already have every modeled field filled in (see diff.resolve_desired).
    `restrictions` is now modeled via `clear_restrictions` — but only as "null or leave alone,"
    not as an arbitrary user/team/app allowlist, since repo-policy has no schema for declaring one
    and the sibling tool this field closes the gap against (see
    docs/superpowers/plans/2026-09-19-clear-restrictions-field.md) never sets one either, only ever
    clears it."""
    current_raw = current_raw or {}
    if resolved.pull_requests is None:
        raise ValueError(
            "resolved.pull_requests must not be None; pass a BranchPolicy produced by "
            "diff.resolve_desired(), which always fills every modeled field"
        )
    return {
        "enforce_admins": bool(resolved.enforce_admins),
        "restrictions": None if resolved.clear_restrictions else current_raw.get("restrictions"),
        "required_pull_request_reviews": pull_requests.to_branch_protection(resolved.pull_requests),
        "required_status_checks": status_checks.to_branch_protection(
            resolved.status_checks, current_raw.get("required_status_checks")
        ),
        "required_linear_history": bool(resolved.linear_history),
        "allow_force_pushes": bool(resolved.allow_force_push),
        "allow_deletions": bool(resolved.allow_deletion),
        "required_conversation_resolution": bool(resolved.required_conversation_resolution),
        "lock_branch": bool(resolved.lock_branch),
        "allow_fork_syncing": bool(resolved.allow_fork_syncing),
    }
```

- [ ] **Step 11: Run to verify pass**

Run: `pytest tests/test_policies_branch_protection.py -v`
Expected: `PASS`, including the pre-existing `test_to_api_payload_preserves_restrictions_from_current_state`.

- [ ] **Step 12: Write the failing `rulesets.py` test in `tests/test_policies_rulesets.py`**

```python
def test_from_api_hardcodes_clear_restrictions_true():
    assert rulesets.from_api(None).clear_restrictions is True
    assert rulesets.from_api({"rules": []}).clear_restrictions is True
```

- [ ] **Step 13: Run to verify failure**

Run: `pytest tests/test_policies_rulesets.py -v -k clear_restrictions`
Expected: `FAIL`

- [ ] **Step 14: Wire the hardcoded constant into `src/repo_policy/policies/rulesets.py`**

Update the existing comment and add `clear_restrictions=True` to both branches of `from_api`:

```python
def from_api(data: dict | None) -> BranchPolicy:
    # enforce_admins/required_conversation_resolution/lock_branch/allow_fork_syncing/
    # clear_restrictions have no GitHub Rulesets equivalent and are rejected for
    # enforcement: ruleset by BranchPolicy's model validator (models.py) -- hardcoded here so
    # resolve_desired()/diff() always report zero drift for them on a ruleset-enforced branch, in
    # every mode.
    if data is None:
        return BranchPolicy(
            enforcement="ruleset",
            pull_requests=PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
            status_checks=None,
            signed_commits=False,
            linear_history=False,
            allow_force_push=True,
            allow_deletion=True,
            enforce_admins=False,
            required_conversation_resolution=False,
            lock_branch=False,
            allow_fork_syncing=True,
            clear_restrictions=True,
        )
    rules_by_type = {rule["type"]: rule for rule in data.get("rules", [])}
    return BranchPolicy(
        enforcement="ruleset",
        pull_requests=pull_requests.from_ruleset_rule(rules_by_type.get("pull_request")),
        status_checks=status_checks.from_ruleset_rule(rules_by_type.get("required_status_checks")),
        signed_commits="required_signatures" in rules_by_type,
        linear_history="required_linear_history" in rules_by_type,
        allow_force_push="non_fast_forward" not in rules_by_type,
        allow_deletion="deletion" not in rules_by_type,
        enforce_admins=False,
        required_conversation_resolution=False,
        lock_branch=False,
        allow_fork_syncing=True,
        clear_restrictions=True,
    )
```

- [ ] **Step 15: Run to verify pass**

Run: `pytest tests/test_policies_rulesets.py -v`
Expected: `PASS`

- [ ] **Step 16: Add the render label**

In `src/repo_policy/render.py`, add to `_LABELS`:

```python
    "clear_restrictions": "Push restrictions",
```

Write the failing test first in `tests/test_render.py`:

```python
def test_render_plan_shows_clear_restrictions_label():
    changes = [Change(field="clear_restrictions", current_value=False, desired_value=True, action="add")]
    output = render_plan("acme/widgets", "main", changes)
    assert "+ Push restrictions" in output
```

Run: `pytest tests/test_render.py -v -k clear_restrictions` — expect `FAIL`, then add the label
line above, then run again — expect `PASS`.

- [ ] **Step 17: Update `tests/test_policies_parity.py`**

Add `clear_restrictions=True` to the `PERMISSIVE` fixture:

```python
PERMISSIVE = BranchPolicy(
    pull_requests=PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
    status_checks=StatusChecksPolicy(required=[]),
    signed_commits=False,
    linear_history=False,
    allow_force_push=True,
    allow_deletion=True,
    enforce_admins=False,
    required_conversation_resolution=False,
    lock_branch=False,
    allow_fork_syncing=True,
    clear_restrictions=True,
)
```

Add `"clear_restrictions": False` to `RESTRICTIVE_VALUES` (the non-permissive value, matching the
same reasoning as Step 1's test):

```python
    "clear_restrictions": False,
```

Add `"clear_restrictions"` to `RULESET_UNSUPPORTED_FIELDS`:

```python
RULESET_UNSUPPORTED_FIELDS = {
    "enforce_admins", "required_conversation_resolution", "lock_branch", "allow_fork_syncing",
    "clear_restrictions",
}
```

- [ ] **Step 18: Run the full suite**

Run: `pytest -v`

**Amendment (found during execution, not anticipated when this plan was written):** the naive
version of Step 17 — leaving `clear_restrictions` in `BRANCH_PROTECTION_FIELDS` alongside every
other field — fails
`test_field_is_represented_by_branch_protection_backend[clear_restrictions]`, and correctly so, not
as a test bug. That test calls `to_api_payload(..., current_raw=None)` for both the permissive
baseline and the field-under-test, which means there's no existing `restrictions` value to preserve
in either case — `clear_restrictions=True` and `=False` both collapse to `restrictions: None` in
the payload when `current_raw` is empty, since there's nothing to leave alone. The fix: exclude
`clear_restrictions` from `BRANCH_PROTECTION_FIELDS`, exactly mirroring the pre-existing
`signed_commits` exclusion in the same file (also excluded because the generic comparison can't
represent it), with a comment explaining why and pointing at the two dedicated
`tests/test_policies_branch_protection.py` tests (Step 8, above) that use a **non-empty**
`current_raw` and do correctly prove the round-trip. Change:

```python
BRANCH_PROTECTION_FIELDS = [f for f in _FIELDS if f != "signed_commits"]
```

to:

```python
# signed_commits is deliberately excluded here: for the branch_protection backend it's handled
# by a separate GitHub endpoint (GitHubClient.set_required_signatures), never by to_api_payload —
# that path is covered by test_apply_branch_sets_signed_commits_separately instead.
#
# clear_restrictions is deliberately excluded too: this test calls to_api_payload with
# current_raw=None for both the baseline and the field-under-test, which means there is no existing
# `restrictions` value to preserve in either case -- clear_restrictions=True and =False both
# collapse to `restrictions: None` in the payload, so this generic comparison can't tell them apart
# (confirmed by actually running it: the assertion fails on real output, not a hypothetical). The
# real round-trip -- clearing an existing restriction vs. preserving one -- is covered directly in
# tests/test_policies_branch_protection.py's test_to_api_payload_forces_restrictions_null_when_clear_restrictions_true
# and test_to_api_payload_preserves_restrictions_when_clear_restrictions_false, both of which pass a
# non-empty current_raw so the distinction is actually observable.
BRANCH_PROTECTION_FIELDS = [f for f in _FIELDS if f not in ("signed_commits", "clear_restrictions")]
```

Expected after this fix: `PASS`, no skips (15 parity tests, `clear_restrictions` correctly absent
from both parametrizes — `BRANCH_PROTECTION_FIELDS` per the above, `RULESET_FIELDS` per
`RULESET_UNSUPPORTED_FIELDS` from Step 17).

- [ ] **Step 19: Run ruff and mypy**

Run: `ruff check .` and `mypy src`
Expected: both clean.

- [ ] **Step 20: Commit**

```bash
git add src/repo_policy/models.py src/repo_policy/diff.py \
  src/repo_policy/policies/branch_protection.py src/repo_policy/policies/rulesets.py \
  src/repo_policy/render.py \
  tests/test_models.py tests/test_diff.py tests/test_policies_branch_protection.py \
  tests/test_policies_rulesets.py tests/test_policies_parity.py tests/test_render.py
git commit -m "feat: model clear_restrictions, closing the last repo_security field gap

Closes the final field-level gap against the sibling repo_security
tool's baseline: GitHub branch-protection restrictions (push allowlist),
which repo_security unconditionally clears to null on every apply.
repo-policy only supports declaring the clear -- not setting an
arbitrary allowlist, since neither repo-policy's schema nor repo_security
itself ever manages one. Branch_protection-only, guarded by the same
ruleset-unsupported-fields validator as enforce_admins/
required_conversation_resolution/lock_branch/allow_fork_syncing."
```

---

### Task 2: Documentation

**Files:**
- Modify: `ARCHITECTURE.md`
- Modify: `ROADMAP.md`

- [ ] **Step 1: Update `ARCHITECTURE.md`'s Domain Model bullet**

Change "ten *optional* policy fields... allow_fork_syncing" to include the eleventh field:

```markdown
- **`BranchPolicy`** — one branch's desired state: `enforcement` (`branch_protection` | `ruleset`,
  default `branch_protection`), an optional per-branch `strict` override, and eleven *optional*
  policy fields (`pull_requests`, `status_checks`, `signed_commits`, `linear_history`,
  `allow_force_push`, `allow_deletion`, `enforce_admins`, `required_conversation_resolution`,
  `lock_branch`, `allow_fork_syncing`, `clear_restrictions`). `None` on any of these eleven means
  "not declared" — this is the single most important modeling choice in the codebase (see
  `docs/adrs/0003-*`). Five of them have no GitHub Rulesets equivalent (the four from Phase 1, plus
  `clear_restrictions` — GitHub Rulesets has no `restrictions`-equivalent concept at all) — a model
  validator on `BranchPolicy` rejects declaring a non-permissive value for any of them on a branch
  with `enforcement: ruleset` at `validate` time, while still allowing the permissive (no-op) value
  through so the same type can represent live ruleset state internally. `PullRequestPolicy`
  additionally carries `dismiss_stale_reviews`/`require_last_push_approval`, which *are* fully
  cross-backend.
```

- [ ] **Step 2: Update `ARCHITECTURE.md`'s Managed-scope bullet under Apply Safety Model**

Change:

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

to:

```markdown
- **Managed-scope (default):** `apply` never touches a branch absent from `policy.yml`. Within a
  declared branch, only the fields present in `policy.yml` are enforced; everything else — for
  `branch_protection`, this now only includes the status-check `strict` field, the one GitHub
  setting the v1 schema still doesn't model at all (`restrictions` became modeled via
  `clear_restrictions`, though only as "null or leave alone," not an arbitrary allowlist — see the
  Domain Model section above) — is read from current state and passed straight through, never
  reset. For `ruleset`, the tool only ever creates/reads/updates a ruleset named
  `repo-policy:<branch>`; it never inspects or modifies any other ruleset.
```

- [ ] **Step 3: Add a row to `ROADMAP.md`'s "Now" table**

```markdown
| Model `clear_restrictions`, closing the last repo_security field gap | Every other field from the sibling tool's baseline was already covered by Phase 1/2; this was the one remaining gap | shipped | TBD |
```

- [ ] **Step 4: Run the full suite one more time**

Run: `pytest -v` / `ruff check .` / `mypy src`
Expected: all clean.

- [ ] **Step 5: Commit**

```bash
git add ARCHITECTURE.md ROADMAP.md
git commit -m "docs: document clear_restrictions and the closed repo_security gap

ARCHITECTURE.md's Domain Model and Apply Safety Model sections corrected
-- restrictions is no longer in the unmodeled-fields list. ROADMAP.md's
Now table gets a row matching the Phase 1/2 convention."
```

---

## Self-Review

**Spec coverage:** `clear_restrictions` field, branch_protection-only guard, both backend
translators, render label, and both fixture updates are each covered by a task step. The
`to_api_payload` docstring correction and the ARCHITECTURE.md prose correction (both flagged as
stale by the field's own addition) are explicit steps, not left implicit.

**Placeholder scan:** No TODO/TBD language in any code step. Step 5 of Task 1 is explicitly marked
as a step that cannot itself fail (fixture-only edit, ahead of the `_FIELDS` change that would make
it matter) — called out rather than presented as a normal failing-test step, matching Phase 1's
precedent for the one genuinely different step in its own Task 3.

**Type consistency:** `clear_restrictions: bool | None` used identically everywhere it appears —
`models.py`, `diff.py`, both `policies/*.py` translators, `render.py`'s label key, and every test
file. No renaming drift.
