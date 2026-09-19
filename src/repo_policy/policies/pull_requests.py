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
