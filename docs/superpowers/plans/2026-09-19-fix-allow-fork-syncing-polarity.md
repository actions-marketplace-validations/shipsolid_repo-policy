# Fix `allow_fork_syncing` Polarity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct `allow_fork_syncing`'s permissive/schema-default value from `True` to `False`, and
add a model validator requiring `lock_branch: true` whenever `allow_fork_syncing: true` is declared
— fixing a real, live-verified bug where GitHub silently discards `allow_fork_syncing: true` on
every branch that doesn't also have `lock_branch: true`, producing permanent phantom drift.

**Architecture:** This is a design correction, not a new field — `docs/superpowers/plans/2026-09-19-branch-protection-field-parity.md`
(Phase 1, Task 5) chose the wrong permissive value for this one field, based on the sibling
`repo_security` tool's baseline rather than live-verified GitHub behavior. The fix has two
independent parts that must both land: (1) flip the *representation* layer — `_SCHEMA_DEFAULTS`,
both backends' `from_api()`, and the ruleset-unsupported-fields validator's permissive-value entry
— so that current-state inheritance and strict-mode defaulting never again produce the broken
`lock_branch: false, allow_fork_syncing: true` pairing without the user asking for it; (2) add a
new model validator (mirroring the existing `RepoSettingsPolicy._automated_security_fixes_requires_vulnerability_alerts`
pattern) that rejects an *explicit* `allow_fork_syncing: true` declaration unless `lock_branch: true`
is also explicitly declared, for the case a user does ask for it. Part 1 fixes the dominant, silent
blast radius (any first-time `apply` on a previously-unprotected branch); part 2 is defense-in-depth
for explicit declarations, since Pydantic's `model_copy()` (used throughout `resolve_desired()`)
does not re-run validators, so a validator alone cannot catch part 1's failure mode.

**Tech Stack:** Python 3.10+, Pydantic v2 — same stack as every prior phase, no new dependencies.

**Spec:** No separate spec doc. Found via live-repo verification against a real GitHub repo
(`shipsolid/playground`) this session, after Phase 1/2/3
(`docs/superpowers/plans/2026-09-19-branch-protection-field-parity.md`,
`docs/superpowers/plans/2026-09-19-repo-level-settings-management.md`,
`docs/superpowers/plans/2026-09-19-clear-restrictions-field.md`, all merged) shipped on mocked
tests only. Confirmed facts below are independently verified against the real GitHub API this
session — not re-derived, not guessed.

## Confirmed Live Facts (do not re-derive — verified this session against a real repo)

- `PUT .../protection` with `{"lock_branch": false, "allow_fork_syncing": true, ...}` in the same
  request → GitHub's response, and every subsequent `GET`, shows `allow_fork_syncing.enabled: false`.
  The `true` value is silently discarded.
- `PUT .../protection` with `{"lock_branch": true, "allow_fork_syncing": true, ...}` → GitHub
  correctly persists `allow_fork_syncing.enabled: true`.
- `PUT .../protection` with `{"lock_branch": false, "allow_fork_syncing": false, ...}` → persists
  correctly as `false`. This combination is always stable regardless of `lock_branch`'s value.
- Conclusion: `allow_fork_syncing: true` is only ever honored by GitHub when `lock_branch: true` is
  set in the *same* state. `allow_fork_syncing: false` is safe and stable in every case.

## The Blast Radius (traced through the actual code, not hypothetical)

`diff._SCHEMA_DEFAULTS["allow_fork_syncing"] = True`, and both `branch_protection.from_api(None, ...)`
and `rulesets.from_api(None)` (plus their populated-data branches' fallback when the key is absent)
currently hardcode `allow_fork_syncing=True` as part of the "nothing configured / fully permissive"
representation — paired with `lock_branch=False` in that same hardcoded return.
`diff.resolve_desired()`'s managed-scope path inherits any undeclared field from `current`. This
means **any first-time `apply` against a previously-unprotected branch that changes any other
field** carries `lock_branch: false, allow_fork_syncing: true` into the same `PUT` body via
inheritance from `current` — even when the user's `policy.yml` never mentions `allow_fork_syncing`
at all. The bug is not limited to `policy.yml` files that explicitly declare
`allow_fork_syncing: true`; it is latent in the default representation of "unprotected branch"
itself, and in `strict` mode's schema-default injection for any branch that leaves this field
undeclared.

## Global Constraints

- `allow_fork_syncing` becomes normal polarity (`False`/unset = empty/no active declaration,
  `True` = an active declaration that requires `lock_branch: true` also be declared) — the same
  shape as `enforce_admins`/`required_conversation_resolution`/`lock_branch`, **not** the
  `allow_force_push`/`allow_deletion` inverted shape it currently shares. Remove it from
  `diff._INVERTED_FIELDS`.
- The new validator only fires when `enforcement == "branch_protection"`. Under
  `enforcement: ruleset`, `allow_fork_syncing: true` remains the *allowed* permissive no-op value
  (per the existing `_reject_ruleset_unsupported_fields` validator), and `lock_branch: true` is
  itself rejected there — requiring the pairing under ruleset enforcement would create an
  impossible, unsatisfiable combination. The two validators check different things and both must
  exist as separate `@model_validator(mode="after")` methods (Pydantic v2 supports multiple on one
  class) — do not merge them.
- `pytest`, `ruff check .`, and `mypy src` clean at every task's commit, not just the plan's end.
- Every commit follows Conventional Commits (`fix: ...`, since this corrects a bug — not `feat:`);
  never hand-edit `CHANGELOG.md`.
- TDD throughout: failing test first, wherever a step is genuinely TDD-able (the representation-flip
  in Task 1 is a coordinated multi-file change with no single meaningful "one red test" — that task
  is structured as "update fixtures/tests to the corrected expectation, confirm they fail against
  the unfixed source, then fix the source," the same pattern Phase 3 used for its `clear_restrictions`
  test-parity blind spot).

---

## File Structure

| File | Change |
|---|---|
| `src/repo_policy/diff.py` | `_SCHEMA_DEFAULTS["allow_fork_syncing"]` flips to `False`; removed from `_INVERTED_FIELDS`; comment above `_INVERTED_FIELDS` corrected |
| `src/repo_policy/policies/branch_protection.py` | `from_api`'s both branches flip `allow_fork_syncing` from `True` to `False` |
| `src/repo_policy/policies/rulesets.py` | `from_api`'s both branches flip `allow_fork_syncing` from `True` to `False` |
| `src/repo_policy/models.py` | `_RULESET_UNSUPPORTED_FIELDS["allow_fork_syncing"]` flips to `False`; new `_allow_fork_syncing_requires_lock_branch` validator on `BranchPolicy` |
| `tests/test_diff.py` | `PERMISSIVE` fixture flips; `test_allow_fork_syncing_inverted_polarity_add_vs_remove` replaced with a normal-polarity, correctly-paired equivalent |
| `tests/test_policies_branch_protection.py` | New test proving the `True` write path when correctly paired with `lock_branch: true` |
| `tests/test_policies_rulesets.py` | `test_from_api_hardcodes_allow_fork_syncing_true` renamed/flipped to assert `False` |
| `tests/test_policies_parity.py` | `PERMISSIVE` fixture and `RESTRICTIVE_VALUES["allow_fork_syncing"]` both flip |
| `tests/test_render.py` | `test_render_plan_shows_fork_syncing_label` updated to the realistic post-fix scenario |
| `tests/test_models.py` | Existing ruleset-rejection test's value flips; new tests for the new validator |
| `docs/test-strategy.md` | New (4th) bug recorded in the "three real bugs" section, matching its existing tone/structure |
| `ROADMAP.md` | One row added to "Now", matching the established Phase 1/2/3 convention |

---

### Task 1: Flip the representation layer (`_SCHEMA_DEFAULTS`, both `from_api()`s, ruleset-unsupported-fields value)

This closes the dominant blast radius: silent, undeclared-field phantom drift on any first-time
`apply`.

**Files:**
- Modify: `src/repo_policy/diff.py`
- Modify: `src/repo_policy/policies/branch_protection.py`
- Modify: `src/repo_policy/policies/rulesets.py`
- Modify: `src/repo_policy/models.py` (`_RULESET_UNSUPPORTED_FIELDS` value only — the new validator is Task 2)
- Test: `tests/test_diff.py`, `tests/test_policies_branch_protection.py`, `tests/test_policies_rulesets.py`, `tests/test_policies_parity.py`, `tests/test_render.py`

**Interfaces:**
- Produces: `allow_fork_syncing`'s permissive value is `False` everywhere in the codebase after this
  task — every later task and every other module treats it identically to `enforce_admins`/
  `lock_branch`/`required_conversation_resolution`.

- [ ] **Step 1: Update `tests/test_diff.py`'s `PERMISSIVE` fixture to the corrected value**

Change:

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

to:

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
    allow_fork_syncing=False,
    clear_restrictions=True,
)
```

- [ ] **Step 2: Replace the inverted-polarity test in `tests/test_diff.py` with a correct normal-polarity equivalent**

Replace:

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

with:

```python
def test_allow_fork_syncing_normal_polarity_add_when_paired_with_lock_branch():
    """allow_fork_syncing is normal polarity, NOT inverted like allow_force_push/allow_deletion --
    False/unset is the stable, always-safe default (see models.py's
    _allow_fork_syncing_requires_lock_branch validator for why True alone is rejected at parse
    time: GitHub silently discards allow_fork_syncing=true unless lock_branch=true is set in the
    same state, confirmed via live-repo verification -- see docs/test-strategy.md). This test
    exercises diff()'s classification for the one combination that's actually valid."""
    current = PERMISSIVE.model_copy(update={"lock_branch": True})
    desired = PERMISSIVE.model_copy(update={"lock_branch": True, "allow_fork_syncing": True})
    changes = diff(desired, current)
    assert len(changes) == 1
    assert changes[0].field == "allow_fork_syncing"
    assert changes[0].action == "add"
```

- [ ] **Step 3: Update `tests/test_policies_parity.py`'s `PERMISSIVE` fixture and `RESTRICTIVE_VALUES`**

Change the `PERMISSIVE` fixture's `allow_fork_syncing=True,` to `allow_fork_syncing=False,`, and
`RESTRICTIVE_VALUES["allow_fork_syncing"]` from:

```python
    "allow_fork_syncing": False,
```

to:

```python
    "allow_fork_syncing": True,
```

- [ ] **Step 4: Update `tests/test_policies_rulesets.py`'s hardcoded-constant test**

Replace:

```python
def test_from_api_hardcodes_allow_fork_syncing_true():
    assert rulesets.from_api(None).allow_fork_syncing is True
    assert rulesets.from_api({"rules": []}).allow_fork_syncing is True
```

with:

```python
def test_from_api_hardcodes_allow_fork_syncing_false():
    assert rulesets.from_api(None).allow_fork_syncing is False
    assert rulesets.from_api({"rules": []}).allow_fork_syncing is False
```

- [ ] **Step 5: Add a paired-write test to `tests/test_policies_branch_protection.py`**

The existing `test_to_api_payload_writes_allow_fork_syncing` (asserting `False` writes as `False`)
stays unchanged — that's still correct behavior. Add a new test right after it proving the `True`
path when correctly paired:

```python
def test_to_api_payload_writes_allow_fork_syncing_true_when_paired_with_lock_branch():
    resolved = BranchPolicy(
        pull_requests=PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
        linear_history=False,
        allow_force_push=True,
        allow_deletion=True,
        lock_branch=True,
        allow_fork_syncing=True,
    )
    payload = branch_protection.to_api_payload(resolved, current_raw=None)
    assert payload["allow_fork_syncing"] is True
    assert payload["lock_branch"] is True
```

- [ ] **Step 6: Update `tests/test_render.py`'s label test to the realistic post-fix scenario**

Change:

```python
def test_render_plan_shows_fork_syncing_label():
    changes = [Change(field="allow_fork_syncing", current_value=True, desired_value=False, action="add")]
    output = render_plan("acme/widgets", "main", changes)
    assert "+ Fork syncing" in output
```

to:

```python
def test_render_plan_shows_fork_syncing_label():
    changes = [Change(field="allow_fork_syncing", current_value=False, desired_value=True, action="add")]
    output = render_plan("acme/widgets", "main", changes)
    assert "+ Fork syncing" in output
```

(`render.py` itself doesn't encode polarity — this change is purely so the test reflects a scenario
that can actually occur post-fix, not a functional requirement.)

- [ ] **Step 7: Run the full suite to confirm these test changes fail against the unfixed source**

Run: `pytest -v`
Expected: several `FAIL`s across `tests/test_diff.py`, `tests/test_policies_branch_protection.py`,
`tests/test_policies_rulesets.py`, `tests/test_policies_parity.py` — the tests now expect the
corrected polarity, but the source still has the old one. This is the "red" half of this task's
TDD cycle; the multi-file nature of the fix means one combined red/green pair rather than many
small ones, matching Phase 3's precedent for its own test-parity correction.

- [ ] **Step 8: Fix `src/repo_policy/diff.py`**

Change `_SCHEMA_DEFAULTS`:

```python
_SCHEMA_DEFAULTS: dict[str, Any] = {
    "pull_requests": PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
    # None, not StatusChecksPolicy(required=[]): branch_protection.from_api / rulesets.from_api
    # both represent "no status checks configured" as None. The strict default must match that
    # exact representation, or a fully-compliant permissive branch shows permanent phantom drift.
    "status_checks": None,
    "signed_commits": False,
    "linear_history": False,
    "allow_force_push": True,
    "allow_deletion": True,
    "enforce_admins": False,
    "required_conversation_resolution": False,
    "lock_branch": False,
    "allow_fork_syncing": False,
    "clear_restrictions": True,
}
```

Change the `_INVERTED_FIELDS` declaration and its comment:

```python
# allow_force_push/allow_deletion have inverted polarity vs. every other field: False means a
# restriction IS present (force push blocked), True means no restriction — the opposite of
# fields like linear_history, where False/empty means no rule exists. allow_fork_syncing is NOT
# inverted, despite superficially resembling these two -- GitHub only honors
# allow_fork_syncing=true when lock_branch=true is also set (see models.py's
# _allow_fork_syncing_requires_lock_branch validator), so False/unset is the safe, always-stable
# default here, not True. Confirmed via live-repo verification -- see docs/test-strategy.md.
_INVERTED_FIELDS = {"allow_force_push", "allow_deletion"}
```

- [ ] **Step 9: Fix `src/repo_policy/policies/branch_protection.py`**

In `from_api`'s `data is None` branch, change `allow_fork_syncing=True,` to
`allow_fork_syncing=False,`. In the populated-data branch, change:

```python
        allow_fork_syncing=_unwrap(data.get("allow_fork_syncing"), True),
```

to:

```python
        allow_fork_syncing=_unwrap(data.get("allow_fork_syncing"), False),
```

(This only changes the fallback used when the key is entirely absent from GitHub's response — real
`GET` responses always include it, so this does not change behavior for any live read; it only
corrects what an unprotected/never-read branch is assumed to be.)

- [ ] **Step 10: Fix `src/repo_policy/policies/rulesets.py`**

In both branches of `from_api` (the `data is None` branch and the populated branch), change
`allow_fork_syncing=True,` to `allow_fork_syncing=False,`.

- [ ] **Step 11: Fix `src/repo_policy/models.py`'s `_RULESET_UNSUPPORTED_FIELDS` value**

Change:

```python
_RULESET_UNSUPPORTED_FIELDS: dict[str, bool] = {
    "enforce_admins": False, "required_conversation_resolution": False, "lock_branch": False,
    "allow_fork_syncing": True,  # inverted polarity: True is the permissive value here
    "clear_restrictions": True,  # True is the permissive value here too: no restriction in effect
}
```

to:

```python
_RULESET_UNSUPPORTED_FIELDS: dict[str, bool] = {
    "enforce_admins": False, "required_conversation_resolution": False, "lock_branch": False,
    "allow_fork_syncing": False, "clear_restrictions": True,
}
```

- [ ] **Step 12: Run the full suite again**

Run: `pytest -v`
Expected: `PASS`, no skips.

- [ ] **Step 13: Run ruff and mypy**

Run: `ruff check .` and `mypy src`
Expected: both clean.

- [ ] **Step 14: Commit**

```bash
git add src/repo_policy/diff.py src/repo_policy/policies/branch_protection.py \
  src/repo_policy/policies/rulesets.py src/repo_policy/models.py \
  tests/test_diff.py tests/test_policies_branch_protection.py tests/test_policies_rulesets.py \
  tests/test_policies_parity.py tests/test_render.py
git commit -m "fix: correct allow_fork_syncing's permissive default from true to false

Found via live-repo verification against a real GitHub repo
(shipsolid/playground): GitHub silently discards allow_fork_syncing:
true on any branch protection PUT where lock_branch is false --
confirmed by pairing them (works) and unpairing them (silently resets
to false) against the real branch-protection API. The old default of
true meant ANY first-time apply against a previously-unprotected
branch inherited lock_branch: false + allow_fork_syncing: true via
resolve_desired()'s managed-scope current-state inheritance, and
strict mode's schema-default injection had the identical problem for
any branch that left the field undeclared -- neither path goes through
model validation (Pydantic's model_copy() skips validators), so this
couldn't have been caught by a validator alone. False is now the
default everywhere: diff._SCHEMA_DEFAULTS, both backends' from_api(),
and the ruleset-unsupported-fields validator's permissive-value entry.
No longer inverted polarity -- removed from diff._INVERTED_FIELDS."
```

---

### Task 2: Add the `allow_fork_syncing` requires `lock_branch` validator

Defense-in-depth for explicit declarations, now that Task 1 has closed the silent/inherited-value
path.

**Files:**
- Modify: `src/repo_policy/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing from Task 1 beyond the corrected permissive value (already landed).
- Produces: `BranchPolicy._allow_fork_syncing_requires_lock_branch` — a new, separate
  `@model_validator(mode="after")` method; does not replace or merge with
  `_reject_ruleset_unsupported_fields`.

- [ ] **Step 1: Fix the now-incorrect existing test in `tests/test_models.py`**

`test_branch_policy_rejects_allow_fork_syncing_under_ruleset` currently declares
`allow_fork_syncing=False` to trigger rejection under `enforcement: ruleset` — but `False` is now
the *permissive* value (Task 1), so it's `True` that should be rejected there now. Change:

```python
def test_branch_policy_rejects_allow_fork_syncing_under_ruleset():
    with pytest.raises(ValidationError, match="allow_fork_syncing"):
        BranchPolicy(enforcement="ruleset", allow_fork_syncing=False)
```

to:

```python
def test_branch_policy_rejects_allow_fork_syncing_under_ruleset():
    with pytest.raises(ValidationError, match="allow_fork_syncing"):
        BranchPolicy(enforcement="ruleset", allow_fork_syncing=True)
```

Leave `test_branch_policy_allows_allow_fork_syncing_under_branch_protection` (which declares
`allow_fork_syncing=False`) unchanged — `False` is still allowed everywhere, unconditionally.

Run: `pytest tests/test_models.py -v -k allow_fork_syncing`
Expected: `PASS` — this step alone doesn't touch the new validator yet, it just corrects a test that
was already broken by Task 1's fix; confirm it's green before adding new tests in Step 2.

- [ ] **Step 2: Write the failing tests for the new validator**

```python
def test_branch_policy_rejects_allow_fork_syncing_true_without_lock_branch():
    with pytest.raises(ValidationError, match="lock_branch"):
        BranchPolicy(enforcement="branch_protection", allow_fork_syncing=True)


def test_branch_policy_rejects_allow_fork_syncing_true_with_lock_branch_false():
    with pytest.raises(ValidationError, match="lock_branch"):
        BranchPolicy(enforcement="branch_protection", allow_fork_syncing=True, lock_branch=False)


def test_branch_policy_allows_allow_fork_syncing_true_with_lock_branch_true():
    policy = BranchPolicy(enforcement="branch_protection", allow_fork_syncing=True, lock_branch=True)
    assert policy.allow_fork_syncing is True
    assert policy.lock_branch is True
```

- [ ] **Step 3: Run to verify failure**

Run: `pytest tests/test_models.py -v -k "allow_fork_syncing_true"`
Expected: `FAIL` on the two `rejects` tests (no validator exists yet to raise), `PASS` on the `allows`
test (nothing currently prevents this combination, since there's no validator yet — a true/true
positive case needs no new code to already pass; confirm this specific one is already green and only
the two rejection tests are red, don't be surprised by the mixed result).

- [ ] **Step 4: Add the new validator to `src/repo_policy/models.py`**

Add directly after `_reject_ruleset_unsupported_fields` inside the `BranchPolicy` class:

```python
    @model_validator(mode="after")
    def _allow_fork_syncing_requires_lock_branch(self) -> BranchPolicy:
        if self.enforcement != "branch_protection":
            return self
        if self.allow_fork_syncing is True and self.lock_branch is not True:
            raise ValueError(
                "allow_fork_syncing: true requires lock_branch: true to also be declared -- "
                "GitHub silently resets allow_fork_syncing back to false whenever lock_branch is "
                "false (confirmed via live-repo verification, see docs/test-strategy.md)"
            )
        return self
```

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/test_models.py -v -k allow_fork_syncing`
Expected: `PASS`, all five tests (the one fixed in Step 1, plus the three new ones, plus the
pre-existing `test_branch_policy_allows_allow_fork_syncing_under_branch_protection`).

- [ ] **Step 6: Run the full suite, ruff, and mypy**

Run: `pytest -v` / `ruff check .` / `mypy src`
Expected: all clean.

- [ ] **Step 7: Commit**

```bash
git add src/repo_policy/models.py tests/test_models.py
git commit -m "fix: reject allow_fork_syncing: true without lock_branch: true

Defense-in-depth alongside Task 1's default-value fix: Pydantic's
model_copy() (used throughout diff.resolve_desired()) skips validators,
so this new validator only catches EXPLICIT policy.yml declarations of
the broken combination -- it cannot see values injected by schema
defaults or current-state inheritance, which is why Task 1's fix to
the underlying representation was the primary correction and this is
the secondary one. Scoped to enforcement: branch_protection only --
under enforcement: ruleset, allow_fork_syncing: true is the allowed
permissive no-op value (existing _reject_ruleset_unsupported_fields
validator), and lock_branch: true is itself rejected there, so
requiring the pairing under ruleset enforcement would be
unsatisfiable."
```

---

### Task 3: Documentation

**Files:**
- Modify: `docs/test-strategy.md`
- Modify: `ROADMAP.md`

- [ ] **Step 1: Add this as bug #4 to `docs/test-strategy.md`**

Change the section heading and intro:

```markdown
## What mocking alone could not catch — four real bugs, found only by testing against a live repo

Mocked tests describe the API the way the author believes it behaves. All four of these bugs
passed a 100%-green mocked suite before being found:
```

Add a fourth numbered item after the existing three:

```markdown
4. **`allow_fork_syncing`'s wrong permissive default.** `diff._SCHEMA_DEFAULTS["allow_fork_syncing"]`
   was `True`, chosen to match the sibling `repo_security` tool's own recommended baseline value —
   never independently verified against live GitHub. **Only surfaced by running `repo-policy apply`
   against a real repository** and independently checking the resulting branch protection via
   `gh api`: GitHub silently discards `allow_fork_syncing: true` on any branch where `lock_branch`
   is `false`, resetting it to `false` regardless of what's sent. Because `True` was also the value
   `from_api(None, ...)` used to represent "nothing configured," `diff.resolve_desired()`'s
   managed-scope current-state inheritance carried the broken pairing into *any* first-time `apply`
   against a previously-unprotected branch — even for a `policy.yml` that never mentions
   `allow_fork_syncing` at all. No mocked test could catch this: it requires a real GitHub API
   response to observe that a value sent in a `PUT` doesn't persist. Fixed by flipping the default
   to `False` (the value GitHub always honors regardless of `lock_branch`) and adding a model
   validator that rejects an explicit `allow_fork_syncing: true` declaration unless `lock_branch:
   true` is also declared — see
   `docs/superpowers/plans/2026-09-19-fix-allow-fork-syncing-polarity.md`.
```

Update the closing paragraph's "all three" reference to "all four":

```markdown
The pattern across all four: the bug was invisible to any test that only asserted repo-policy's
own internal consistency. Each one required checking repo-policy's output against an independent,
real source of truth — a live repo's actual API state, or a real PyPI install.
```

- [ ] **Step 2: Add a row to `ROADMAP.md`'s "Now" table**

```markdown
| Fix allow_fork_syncing's wrong permissive default | Found via live-repo verification: GitHub silently discards allow_fork_syncing: true unless lock_branch: true is also set, causing permanent phantom drift on any first-time apply | shipped | TBD |
```

- [ ] **Step 3: Run the full suite one more time**

Run: `pytest -v` / `ruff check .` / `mypy src`
Expected: all clean.

- [ ] **Step 4: Commit**

```bash
git add docs/test-strategy.md ROADMAP.md
git commit -m "docs: record the allow_fork_syncing bug as the 4th live-testing find

docs/test-strategy.md's 'three real bugs' section becomes four,
matching its existing tone and structure. ROADMAP.md's Now table gets
a row matching the established Phase 1/2/3 convention."
```

---

## Self-Review

**Spec coverage:** Both required parts of the fix (representation-layer flip in Task 1, new
validator in Task 2) are covered, in the order that matches their actual blast radius (dominant
silent path first, explicit-declaration defense-in-depth second). Every file the initial research
grep found (`tests/test_models.py`, `tests/test_diff.py`, `tests/test_policies_branch_protection.py`,
`tests/test_policies_rulesets.py`, `tests/test_policies_parity.py`, `tests/test_render.py`, plus the
four source files) has a task step. `ARCHITECTURE.md` was checked and needs no change — it only
lists the field name in an enumeration, with no polarity-specific claim to correct. No ADR
references this field's polarity.

**Placeholder scan:** No TODO/TBD language in any code step. Task 1 Step 7's "expect failures, this
is the red half" is an explicit, explained deviation from the usual one-test-at-a-time red/green
cycle, matching the multi-file nature of a coordinated default-value flip — not a placeholder.

**Type consistency:** `allow_fork_syncing: bool | None` and `lock_branch: bool | None` referenced
identically (same names, same `True`/`False`/`None` semantics) across `models.py`, `diff.py`, both
`policies/*.py` translators, and every test file touched. The new validator method name
(`_allow_fork_syncing_requires_lock_branch`) is used consistently between its Task 2 Step 4
definition and nowhere else needs to reference it by name (it's a Pydantic hook, not called
directly).
