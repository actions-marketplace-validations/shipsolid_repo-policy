from __future__ import annotations

from repo_policy.models import PullRequestPolicy


def to_branch_protection(policy: PullRequestPolicy) -> dict | None:
    if not policy.required:
        return None
    return {
        "required_approving_review_count": policy.approvals,
        "require_code_owner_reviews": policy.code_owner_review,
        "dismiss_stale_reviews": False,
        "require_last_push_approval": False,
    }


def from_branch_protection(data: dict | None) -> PullRequestPolicy:
    if data is None:
        return PullRequestPolicy(required=False, approvals=0, code_owner_review=False)
    return PullRequestPolicy(
        required=True,
        approvals=data.get("required_approving_review_count", 0),
        code_owner_review=data.get("require_code_owner_reviews", False),
    )


def to_ruleset_rule(policy: PullRequestPolicy) -> dict | None:
    if not policy.required:
        return None
    return {
        "type": "pull_request",
        "parameters": {
            "required_approving_review_count": policy.approvals,
            "require_code_owner_review": policy.code_owner_review,
            "require_last_push_approval": False,
            "dismiss_stale_reviews_on_push": False,
            "required_review_thread_resolution": False,
        },
    }


def from_ruleset_rule(rule: dict | None) -> PullRequestPolicy:
    if rule is None:
        return PullRequestPolicy(required=False, approvals=0, code_owner_review=False)
    params = rule["parameters"]
    return PullRequestPolicy(
        required=True,
        approvals=params.get("required_approving_review_count", 0),
        code_owner_review=params.get("require_code_owner_review", False),
    )
