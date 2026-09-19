from __future__ import annotations

from dataclasses import dataclass

from repo_policy.apply import detect_stale_branch_protection, plan_branch, prefetch_rulesets
from repo_policy.diff import Change
from repo_policy.github_client import GitHubClient
from repo_policy.models import PolicyConfig


@dataclass
class AuditResult:
    branch: str
    changes: list[Change]
    stale_branch_protection: bool = False

    @property
    def compliant(self) -> bool:
        return not self.changes and not self.stale_branch_protection


def audit_all(client: GitHubClient, config: PolicyConfig) -> list[AuditResult]:
    rulesets_cache = prefetch_rulesets(client, config)
    stale_branches = set(detect_stale_branch_protection(client, config))
    results = []
    for branch in config.branches:
        changes, _resolved = plan_branch(client, config, branch, rulesets_cache=rulesets_cache)
        results.append(
            AuditResult(branch=branch, changes=changes, stale_branch_protection=branch in stale_branches)
        )
    return results
