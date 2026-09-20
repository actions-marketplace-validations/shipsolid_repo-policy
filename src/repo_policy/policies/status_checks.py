from __future__ import annotations

from repo_policy.models import StatusChecksPolicy


def to_branch_protection(policy: StatusChecksPolicy | None, current: dict | None = None) -> dict | None:
    """`current` is the branch's existing required_status_checks GET payload (or None on first
    creation). repo-policy doesn't model the 'require branches up to date' (strict) setting, so
    it's read through from current state rather than reset to False on every apply."""
    if policy is None or not policy.required:
        return None
    current = current or {}
    return {
        "strict": current.get("strict", False),
        "contexts": list(policy.required),
        "checks": [{"context": name, "app_id": None} for name in policy.required],
    }


def from_branch_protection(data: dict | None) -> StatusChecksPolicy | None:
    if data is None:
        return None
    contexts = data.get("contexts") or [check["context"] for check in data.get("checks", [])]
    if not contexts:
        return None
    return StatusChecksPolicy(required=list(contexts))


def to_ruleset_rule(policy: StatusChecksPolicy | None, current: dict | None = None) -> dict | None:
    """`current` is the existing rules-array entry of type "required_status_checks" (or None on
    first creation). repo-policy doesn't model strict_required_status_checks_policy or
    do_not_enforce_on_create, so both are read through from current state rather than reset on
    every apply -- the ruleset-backend counterpart of to_branch_protection()'s `current`
    read-through, for the exact same reason."""
    if policy is None or not policy.required:
        return None
    current_params = current.get("parameters", {}) if current is not None else {}
    return {
        "type": "required_status_checks",
        "parameters": {
            "required_status_checks": [{"context": name} for name in policy.required],
            "strict_required_status_checks_policy": current_params.get(
                "strict_required_status_checks_policy", False
            ),
            "do_not_enforce_on_create": current_params.get("do_not_enforce_on_create", False),
        },
    }


def from_ruleset_rule(rule: dict | None) -> StatusChecksPolicy | None:
    if rule is None:
        return None
    checks = rule["parameters"].get("required_status_checks", [])
    if not checks:
        return None
    return StatusChecksPolicy(required=[check["context"] for check in checks])
