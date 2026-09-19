from __future__ import annotations

from repo_policy.models import _RULESET_UNSUPPORTED_FIELDS, BranchPolicy, PullRequestPolicy
from repo_policy.policies import pull_requests, status_checks


def ruleset_name(branch: str) -> str:
    return f"repo-policy:{branch}"


# Every rule type to_api_payload actually builds. GitHub Rulesets support many more (e.g.
# commit_message_pattern, tag_name_pattern, merge_queue, workflows) that repo-policy has no
# schema for -- a human-added rule of one of those types must survive a full-object replace
# triggered by an unrelated, modeled field changing, not be silently dropped.
_MANAGED_RULE_TYPES = {
    "pull_request",
    "required_status_checks",
    "required_signatures",
    "required_linear_history",
    "non_fast_forward",
    "deletion",
}


def from_api(data: dict | None) -> BranchPolicy:
    # enforce_admins/required_conversation_resolution/lock_branch/allow_fork_syncing/
    # clear_restrictions have no GitHub Rulesets equivalent and are rejected for
    # enforcement: ruleset by BranchPolicy's model validator (models.py) -- hardcoded (via
    # models._RULESET_UNSUPPORTED_FIELDS, the single source of truth for these permissive values)
    # so resolve_desired()/diff() always report zero drift for them on a ruleset-enforced branch,
    # in every mode.
    if data is None:
        return BranchPolicy(
            enforcement="ruleset",
            pull_requests=PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
            status_checks=None,
            signed_commits=False,
            linear_history=False,
            allow_force_push=True,
            allow_deletion=True,
            **_RULESET_UNSUPPORTED_FIELDS,
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
        **_RULESET_UNSUPPORTED_FIELDS,
    )


def to_api_payload(branch: str, resolved: BranchPolicy, current_raw: dict | None = None) -> dict:
    """`resolved` must already have every modeled field filled in (see diff.resolve_desired).
    Rulesets are fully owned by repo-policy once named, so this rebuilds the rules array for
    every MODELED field -- but strict_required_status_checks_policy, `enforcement`
    (active/evaluate/disabled), `bypass_actors`, and any rule of an unmodeled type (see
    _MANAGED_RULE_TYPES) have no modeled field (see status_checks.to_ruleset_rule for the first),
    so `current_raw` (the ruleset's current GET payload, or None on first creation) is threaded
    through to preserve all of them instead of resetting/dropping them on every apply.
    `enforcement` defaults to "active" and `bypass_actors` to an empty list only when there's no
    current state to read from (first creation)."""
    if resolved.pull_requests is None:
        raise ValueError(
            "resolved.pull_requests must not be None; pass a BranchPolicy produced by "
            "diff.resolve_desired(), which always fills every modeled field"
        )
    current_raw = current_raw or {}
    current_rules_by_type = {rule["type"]: rule for rule in current_raw.get("rules", [])}
    # Carry forward any existing rule of a type repo-policy doesn't model at all, verbatim.
    rules: list[dict] = [
        rule for rule in current_raw.get("rules", []) if rule["type"] not in _MANAGED_RULE_TYPES
    ]

    pr_rule = pull_requests.to_ruleset_rule(resolved.pull_requests)
    if pr_rule is not None:
        rules.append(pr_rule)

    sc_rule = status_checks.to_ruleset_rule(
        resolved.status_checks, current=current_rules_by_type.get("required_status_checks")
    )
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
        "enforcement": current_raw.get("enforcement", "active"),
        "conditions": {"ref_name": {"include": [f"refs/heads/{branch}"], "exclude": []}},
        "rules": rules,
        "bypass_actors": current_raw.get("bypass_actors", []),
    }
