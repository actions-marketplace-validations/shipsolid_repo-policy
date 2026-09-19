from __future__ import annotations

from repo_policy.diff import Change

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
