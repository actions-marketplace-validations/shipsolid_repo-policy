from __future__ import annotations

from repo_policy.diff import Change
from repo_policy.repo_settings import RepoSettingsResult

_SYMBOLS = {"add": "+", "modify": "~", "remove": "-"}

_LABELS = {
    "pull_requests": "Pull request requirements",
    "status_checks": "Required status checks",
    "signed_commits": "Signed commits",
    "linear_history": "Linear history",
    "allow_force_push": "Force pushes",
    "allow_deletion": "Branch deletion",
    "enforce_admins": "Admin enforcement",
    "required_conversation_resolution": "Conversation resolution",
    "lock_branch": "Branch lock",
    "allow_fork_syncing": "Fork syncing",
}

_REPO_SETTINGS_LABELS = {
    "delete_branch_on_merge": "Delete branch on merge",
    "allow_update_branch": "Allow update branch",
    "vulnerability_alerts": "Dependabot alerts",
    "automated_security_fixes": "Dependabot security updates",
    "private_vulnerability_reporting": "Private vulnerability reporting",
    "secret_scanning": "Secret scanning",
    "secret_scanning_push_protection": "Secret scanning push protection",
}


def render_plan(repo: str, branch: str, changes: list[Change]) -> str:
    changed_fields = {change.field for change in changes}
    lines = [f"Repository: {repo}", f"Branch: {branch}", ""]

    for field, label in _LABELS.items():
        if field not in changed_fields:
            lines.append(f"✓ {label}")

    for change in changes:
        symbol = _SYMBOLS[change.action]
        label = _LABELS[change.field]
        lines.append(f"{symbol} {label:<28} {change.current_value} → {change.desired_value}")

    lines.append("")
    if not changes:
        lines.append("No changes required.")
    else:
        noun = "change" if len(changes) == 1 else "changes"
        lines.append(f"{len(changes)} {noun} required.")

    return "\n".join(lines)


def render_repo_settings(repo: str, result: RepoSettingsResult) -> str:
    lines = [f"Repository: {repo}", "Repo-level settings:", ""]

    for change in result.changes:
        symbol = _SYMBOLS[change.action]
        label = _REPO_SETTINGS_LABELS.get(change.field, change.field)
        lines.append(f"{symbol} {label:<28} {change.current_value} → {change.desired_value}")

    for field_name in result.unavailable:
        label = _REPO_SETTINGS_LABELS.get(field_name, field_name)
        lines.append(f"? {label:<28} unavailable on this repository")

    lines.append("")
    if not result.changes and not result.unavailable:
        lines.append("No repo-level setting changes required.")
    else:
        noun = "change" if len(result.changes) == 1 else "changes"
        lines.append(f"{len(result.changes)} {noun} required.")

    return "\n".join(lines)
