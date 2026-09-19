from __future__ import annotations

from dataclasses import dataclass, field

from repo_policy.github_client import GitHubClient
from repo_policy.models import PolicyConfig
from repo_policy.policies.repo_settings import (
    _FLAT_FIELDS,
    _SECURITY_AND_ANALYSIS_FIELDS,
    RepoSettingChange,
    diff_flat_settings,
    diff_security_and_analysis,
    diff_toggle,
    to_flat_settings_payload,
    to_security_and_analysis_payload,
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
    result.changes.extend(diff_security_and_analysis(current_repo, desired))

    if desired.vulnerability_alerts is not None:
        current = client.get_vulnerability_alerts()
        result.changes.extend(diff_toggle("vulnerability_alerts", current, desired.vulnerability_alerts))

    if desired.automated_security_fixes is not None:
        current = client.get_automated_security_fixes()
        result.changes.extend(diff_toggle("automated_security_fixes", current, desired.automated_security_fixes))

    if desired.private_vulnerability_reporting is not None:
        current_pvr = client.get_private_vulnerability_reporting()
        if current_pvr is None:
            result.unavailable.append("private_vulnerability_reporting")
        else:
            result.changes.extend(
                diff_toggle("private_vulnerability_reporting", current_pvr, desired.private_vulnerability_reporting)
            )

    return result


def apply_repo_settings(client: GitHubClient, config: PolicyConfig) -> RepoSettingsResult:
    desired = config.repo_settings
    if desired is None:
        return RepoSettingsResult()

    result = plan_repo_settings(client, config)

    flat_changes = [c for c in result.changes if c.field in _FLAT_FIELDS]
    if flat_changes:
        client.update_repo_settings(to_flat_settings_payload(flat_changes))

    security_changes = [c for c in result.changes if c.field in _SECURITY_AND_ANALYSIS_FIELDS]
    if security_changes:
        outcome = client.update_security_and_analysis(to_security_and_analysis_payload(security_changes))
        if outcome is None:
            result.unavailable.extend(sorted({c.field for c in security_changes}))

    changed_fields = {c.field for c in result.changes}
    if "vulnerability_alerts" in changed_fields:
        if desired.vulnerability_alerts:
            client.enable_vulnerability_alerts()
        else:
            client.disable_vulnerability_alerts()

    # Must run after vulnerability_alerts, above -- GitHub requires Dependabot alerts enabled
    # before Dependabot security updates can be turned on. RepoSettingsPolicy's model validator
    # (models.py) already guarantees automated_security_fixes=True never appears without
    # vulnerability_alerts=True declared, but that only constrains what's *declared* -- this
    # ordering is what makes the two live API calls land in the right sequence.
    if "automated_security_fixes" in changed_fields:
        if desired.automated_security_fixes:
            client.enable_automated_security_fixes()
        else:
            client.disable_automated_security_fixes()

    if "private_vulnerability_reporting" in changed_fields:
        if desired.private_vulnerability_reporting:
            applied = client.enable_private_vulnerability_reporting()
        else:
            applied = client.disable_private_vulnerability_reporting()
        if not applied:
            result.unavailable.append("private_vulnerability_reporting")

    result.applied = any(change.field not in result.unavailable for change in result.changes)
    return result
