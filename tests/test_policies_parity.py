"""Cross-backend parity guard.

branch_protection.py and rulesets.py each hand-write their own full-payload translation with no
shared source of truth (see the design spec's discussion of why they're separate modules). That
duplication is exactly how the dismiss_stale_reviews/strict clobber bug slipped in undetected:
a field handled by one backend had no representation in the other's tests. This file iterates
every field in diff._FIELDS and asserts both backends actually respond to it, so a future field
addition that's wired into only one translator fails loudly here instead of shipping silently.
"""
import pytest

from repo_policy.diff import _FIELDS
from repo_policy.models import BranchPolicy, PullRequestPolicy, StatusChecksPolicy
from repo_policy.policies import branch_protection, rulesets

PERMISSIVE = BranchPolicy(
    pull_requests=PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
    status_checks=StatusChecksPolicy(required=[]),
    signed_commits=False,
    linear_history=False,
    allow_force_push=True,
    allow_deletion=True,
)

RESTRICTIVE_VALUES = {
    "pull_requests": PullRequestPolicy(
        required=True, approvals=2, code_owner_review=True,
        dismiss_stale_reviews=True, require_last_push_approval=True,
    ),
    "status_checks": StatusChecksPolicy(required=["build"]),
    "signed_commits": True,
    "linear_history": True,
    "allow_force_push": False,
    "allow_deletion": False,
    "enforce_admins": True,
    "required_conversation_resolution": True,
}

# signed_commits is deliberately excluded here: for the branch_protection backend it's handled
# by a separate GitHub endpoint (GitHubClient.set_required_signatures), never by to_api_payload —
# that path is covered by test_apply_branch_sets_signed_commits_separately instead.
BRANCH_PROTECTION_FIELDS = [f for f in _FIELDS if f != "signed_commits"]

# enforce_admins/required_conversation_resolution/lock_branch/allow_fork_syncing have no GitHub
# Rulesets equivalent -- BranchPolicy's model validator (models.py) rejects setting them under
# enforcement: ruleset, so the ruleset backend never needs to represent them (see rulesets.from_api,
# which hardcodes each to its permissive constant instead of reading it).
RULESET_UNSUPPORTED_FIELDS = {
    "enforce_admins", "required_conversation_resolution", "lock_branch", "allow_fork_syncing",
}
RULESET_FIELDS = [f for f in _FIELDS if f not in RULESET_UNSUPPORTED_FIELDS]


@pytest.mark.parametrize("field", BRANCH_PROTECTION_FIELDS)
def test_field_is_represented_by_branch_protection_backend(field):
    resolved = PERMISSIVE.model_copy(update={field: RESTRICTIVE_VALUES[field]})
    baseline = branch_protection.to_api_payload(PERMISSIVE, current_raw=None)
    payload = branch_protection.to_api_payload(resolved, current_raw=None)
    assert payload != baseline, f"branch_protection backend ignores field {field!r}"


@pytest.mark.parametrize("field", RULESET_FIELDS)
def test_field_is_represented_by_ruleset_backend(field):
    resolved = PERMISSIVE.model_copy(update={field: RESTRICTIVE_VALUES[field]})
    baseline_rules = rulesets.to_api_payload("main", PERMISSIVE)["rules"]
    payload_rules = rulesets.to_api_payload("main", resolved)["rules"]
    assert payload_rules != baseline_rules, f"ruleset backend ignores field {field!r}"
