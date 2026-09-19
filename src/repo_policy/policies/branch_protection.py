from __future__ import annotations

from repo_policy.models import BranchPolicy, PullRequestPolicy
from repo_policy.policies import pull_requests, status_checks


def _unwrap(value: object, default: bool) -> bool:
    """GitHub's GET response wraps some booleans as {"enabled": bool}; PUT wants raw bool."""
    if isinstance(value, dict):
        return bool(value.get("enabled", default))
    if value is None:
        return default
    return bool(value)


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
    )


def to_api_payload(resolved: BranchPolicy, current_raw: dict | None) -> dict:
    """`resolved` must already have every modeled field filled in (see diff.resolve_desired) —
    this only reads `current_raw` for `restrictions`, the one PUT-required field the v1 schema
    still doesn't model, preserving whatever is already there."""
    current_raw = current_raw or {}
    if resolved.pull_requests is None:
        raise ValueError(
            "resolved.pull_requests must not be None; pass a BranchPolicy produced by "
            "diff.resolve_desired(), which always fills every modeled field"
        )
    return {
        "enforce_admins": bool(resolved.enforce_admins),
        "restrictions": current_raw.get("restrictions"),
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
