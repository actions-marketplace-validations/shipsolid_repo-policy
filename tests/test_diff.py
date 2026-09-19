from repo_policy.diff import diff, resolve_desired
from repo_policy.models import BranchPolicy, PullRequestPolicy, StatusChecksPolicy

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


def test_diff_empty_when_equal():
    assert diff(PERMISSIVE, PERMISSIVE) == []


def test_diff_detects_modify():
    desired = PERMISSIVE.model_copy(update={"linear_history": True})
    changes = diff(desired, PERMISSIVE)
    assert len(changes) == 1
    assert changes[0].field == "linear_history"
    assert changes[0].action == "add"


def test_diff_detects_approvals_increase_as_modify():
    current = PERMISSIVE.model_copy(
        update={"pull_requests": PullRequestPolicy(required=True, approvals=1, code_owner_review=False)}
    )
    desired = PERMISSIVE.model_copy(
        update={"pull_requests": PullRequestPolicy(required=True, approvals=2, code_owner_review=False)}
    )
    changes = diff(desired, current)
    assert len(changes) == 1
    assert changes[0].field == "pull_requests"
    assert changes[0].action == "modify"


def test_diff_detects_remove():
    current = PERMISSIVE.model_copy(update={"allow_force_push": False})
    desired = PERMISSIVE.model_copy(update={"allow_force_push": True})
    changes = diff(desired, current)
    assert len(changes) == 1
    assert changes[0].action == "remove"


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


def test_resolve_desired_managed_scope_inherits_current_for_unset_fields():
    desired = BranchPolicy(linear_history=True)  # everything else left unset
    current = PERMISSIVE.model_copy(
        update={"pull_requests": PullRequestPolicy(required=True, approvals=3, code_owner_review=True)}
    )
    resolved = resolve_desired(desired, current, strict=False)
    assert resolved.linear_history is True
    assert resolved.pull_requests == PullRequestPolicy(required=True, approvals=3, code_owner_review=True)
    changes = diff(resolved, current)
    assert len(changes) == 1
    assert changes[0].field == "linear_history"


def test_resolve_desired_strict_uses_schema_defaults_for_unset_fields():
    desired = BranchPolicy(linear_history=True)
    current = BranchPolicy(
        pull_requests=PullRequestPolicy(required=True, approvals=3, code_owner_review=True),
        status_checks=StatusChecksPolicy(required=["build"]),
        signed_commits=True,
        linear_history=False,
        allow_force_push=False,
        allow_deletion=False,
    )
    resolved = resolve_desired(desired, current, strict=True)
    assert resolved.pull_requests == PullRequestPolicy(required=False, approvals=0, code_owner_review=False)
    assert resolved.status_checks is None
    assert resolved.signed_commits is False
    assert resolved.allow_force_push is True
    assert resolved.allow_deletion is True
    # strict still respects fields the branch DID declare
    assert resolved.linear_history is True


def test_strict_mode_reports_no_drift_for_an_already_compliant_permissive_branch():
    """Regression test: found via live testing against a real repo. A branch with no status
    checks configured normalizes to status_checks=None (see branch_protection.from_api /
    rulesets.from_api), not StatusChecksPolicy(required=[]) -- the strict schema default must
    match that exact representation, or strict mode reports permanent phantom drift and issues
    an unnecessary API call on every single apply."""
    desired = PERMISSIVE.model_copy(update={"linear_history": True})
    current = PERMISSIVE.model_copy(update={"linear_history": True})
    resolved = resolve_desired(desired, current, strict=True)
    assert diff(resolved, current) == []
