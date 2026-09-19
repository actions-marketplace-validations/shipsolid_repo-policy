from __future__ import annotations

from repo_policy.models import StatusChecksPolicy


def to_branch_protection(policy: StatusChecksPolicy | None) -> dict | None:
    if policy is None or not policy.required:
        return None
    return {
        "strict": False,
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


def to_ruleset_rule(policy: StatusChecksPolicy | None) -> dict | None:
    if policy is None or not policy.required:
        return None
    return {
        "type": "required_status_checks",
        "parameters": {
            "required_status_checks": [{"context": name} for name in policy.required],
            "strict_required_status_checks_policy": False,
        },
    }


def from_ruleset_rule(rule: dict | None) -> StatusChecksPolicy | None:
    if rule is None:
        return None
    checks = rule["parameters"].get("required_status_checks", [])
    if not checks:
        return None
    return StatusChecksPolicy(required=[check["context"] for check in checks])
