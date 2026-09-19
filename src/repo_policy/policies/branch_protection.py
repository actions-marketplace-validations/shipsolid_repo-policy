from __future__ import annotations

from repo_policy.github_client import _unwrap
from repo_policy.models import BranchPolicy, PullRequestPolicy
from repo_policy.policies import pull_requests, status_checks


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
            allow_fork_syncing=False,
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
        allow_fork_syncing=_unwrap(data.get("allow_fork_syncing"), False),
        clear_restrictions=data.get("restrictions") is None,
    )


def _restrictions_payload(current_restrictions: dict | None) -> dict | None:
    """GitHub's GET response shapes restrictions.users/teams/apps as arrays of full objects
    (login/slug plus other metadata); the PUT request body expects arrays of bare login/slug
    strings. Sending the GET shape back verbatim 422s -- this is the transform between the two."""
    if current_restrictions is None:
        return None
    return {
        "users": [user["login"] for user in current_restrictions.get("users", [])],
        "teams": [team["slug"] for team in current_restrictions.get("teams", [])],
        "apps": [app["slug"] for app in current_restrictions.get("apps", [])],
    }


def to_api_payload(resolved: BranchPolicy, current_raw: dict | None) -> dict:
    """`resolved` must already have every modeled field filled in (see diff.resolve_desired).
    `restrictions` is now modeled via `clear_restrictions` — but only as "null or leave alone,"
    not as an arbitrary user/team/app allowlist, since repo-policy has no schema for declaring one
    and the sibling tool this field closes the gap against (see commit 9abd10a, "model
    clear_restrictions, closing the last repo_security field gap") never sets one either, only
    ever clears it. `block_creations` has no modeled field at all -- read through from
    `current_raw` the same way status_checks.to_branch_protection's `strict` is, so it isn't
    silently reset to False by an unrelated declared change."""
    current_raw = current_raw or {}
    if resolved.pull_requests is None:
        raise ValueError(
            "resolved.pull_requests must not be None; pass a BranchPolicy produced by "
            "diff.resolve_desired(), which always fills every modeled field"
        )
    return {
        "enforce_admins": bool(resolved.enforce_admins),
        "block_creations": _unwrap(current_raw.get("block_creations"), False),
        "restrictions": (
            None if resolved.clear_restrictions
            else _restrictions_payload(current_raw.get("restrictions"))
        ),
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
