from __future__ import annotations

from repo_policy.github_client import _actor_refs
from repo_policy.models import PullRequestPolicy


def to_branch_protection(policy: PullRequestPolicy, current: dict | None = None) -> dict | None:
    """dismiss_stale_reviews/require_last_push_approval are modeled directly on PullRequestPolicy
    (previously read through from current state — see commit 41e59cb, "model
    dismiss_stale_reviews and require_last_push_approval", for why that changed).
    dismissal_restrictions/bypass_pull_request_allowances have no modeled field at all -- `current`
    is the branch's existing required_pull_request_reviews GET payload (or None on first
    creation), read through the same way status_checks.to_branch_protection's `strict` is, so a
    human-set allow-list isn't silently reset to empty by an unrelated declared change. Omitted
    entirely (not sent as an empty allow-list) when there's no current state to read from."""
    if not policy.required:
        return None
    current = current or {}
    payload: dict[str, object] = {
        "required_approving_review_count": policy.approvals,
        "require_code_owner_reviews": policy.code_owner_review,
        "dismiss_stale_reviews": policy.dismiss_stale_reviews,
        "require_last_push_approval": policy.require_last_push_approval,
    }
    if current.get("dismissal_restrictions") is not None:
        payload["dismissal_restrictions"] = _actor_refs(current["dismissal_restrictions"])
    if current.get("bypass_pull_request_allowances") is not None:
        payload["bypass_pull_request_allowances"] = _actor_refs(current["bypass_pull_request_allowances"])
    return payload


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
