from __future__ import annotations

from dataclasses import dataclass, field

from repo_policy.github_client import GitHubClient
from repo_policy.models import PolicyConfig
from repo_policy.policies.repo_settings import (
    RepoSettingChange,
    diff_flat_settings,
    diff_toggle,
    to_flat_settings_payload,
)


@dataclass
class RepoSettingsResult:
    changes: list[RepoSettingChange] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)
    applied: bool = False


def plan_repo_settings(client: GitHubClient, config: PolicyConfig) -> RepoSettingsResult:
    """Read-only: fetch current state and diff against policy.yml's repo_settings section. Makes
    zero API calls and returns an empty result when the section isn't declared at all."""
    desired = config.repo_settings
    if desired is None:
        return RepoSettingsResult()

    result = RepoSettingsResult()
    current_repo = client.get_repo()
    result.changes.extend(diff_flat_settings(current_repo, desired))

    if desired.vulnerability_alerts is not None:
        current = client.get_vulnerability_alerts()
        result.changes.extend(diff_toggle("vulnerability_alerts", current, desired.vulnerability_alerts))

    if desired.automated_security_fixes is not None:
        current = client.get_automated_security_fixes()
        result.changes.extend(diff_toggle("automated_security_fixes", current, desired.automated_security_fixes))

    return result


def apply_repo_settings(client: GitHubClient, config: PolicyConfig) -> RepoSettingsResult:
    desired = config.repo_settings
    if desired is None:
        return RepoSettingsResult()

    result = plan_repo_settings(client, config)

    flat_changes = [c for c in result.changes if c.field in ("delete_branch_on_merge", "allow_update_branch")]
    if flat_changes:
        client.update_repo_settings(to_flat_settings_payload(flat_changes))

    changed_fields = {c.field for c in result.changes}
    if "vulnerability_alerts" in changed_fields:
        client.enable_vulnerability_alerts()

    # Must run after vulnerability_alerts, above -- GitHub requires Dependabot alerts enabled
    # before Dependabot security updates can be turned on. RepoSettingsPolicy's model validator
    # (models.py) already guarantees automated_security_fixes=True never appears without
    # vulnerability_alerts=True declared, but that only constrains what's *declared* -- this
    # ordering is what makes the two live API calls land in the right sequence.
    if "automated_security_fixes" in changed_fields:
        client.enable_automated_security_fixes()

    result.applied = bool(result.changes)
    return result
