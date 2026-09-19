from __future__ import annotations

from repo_policy.models import BranchPolicy, PullRequestPolicy
from repo_policy.policies import pull_requests, status_checks


def ruleset_name(branch: str) -> str:
    return f"repo-policy:{branch}"


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
            allow_fork_syncing=False,
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
        allow_fork_syncing=False,
        clear_restrictions=True,
    )


def to_api_payload(branch: str, resolved: BranchPolicy) -> dict:
    """`resolved` must already have every modeled field filled in (see diff.resolve_desired).
    Rulesets are fully owned by repo-policy once named, so this is a full replace of the rules
    array — there are no unmodeled fields to preserve, unlike branch_protection.to_api_payload."""
    if resolved.pull_requests is None:
        raise ValueError(
            "resolved.pull_requests must not be None; pass a BranchPolicy produced by "
            "diff.resolve_desired(), which always fills every modeled field"
        )
    rules: list[dict] = []

    pr_rule = pull_requests.to_ruleset_rule(resolved.pull_requests)
    if pr_rule is not None:
        rules.append(pr_rule)

    sc_rule = status_checks.to_ruleset_rule(resolved.status_checks)
    if sc_rule is not None:
        rules.append(sc_rule)

    if resolved.signed_commits:
        rules.append({"type": "required_signatures"})
    if resolved.linear_history:
        rules.append({"type": "required_linear_history"})
    if resolved.allow_force_push is False:
        rules.append({"type": "non_fast_forward"})
    if resolved.allow_deletion is False:
        rules.append({"type": "deletion"})

    return {
        "name": ruleset_name(branch),
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": [f"refs/heads/{branch}"], "exclude": []}},
        "rules": rules,
    }
