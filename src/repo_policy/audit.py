from __future__ import annotations

from dataclasses import dataclass

from repo_policy.apply import plan_branch, prefetch_rulesets
from repo_policy.diff import Change
from repo_policy.github_client import GitHubClient
from repo_policy.models import PolicyConfig


@dataclass
class AuditResult:
    branch: str
    changes: list[Change]

    @property
    def compliant(self) -> bool:
        return not self.changes


def audit_all(client: GitHubClient, config: PolicyConfig) -> list[AuditResult]:
    rulesets_cache = prefetch_rulesets(client, config)
    results = []
    for branch in config.branches:
        changes, _resolved = plan_branch(client, config, branch, rulesets_cache=rulesets_cache)
        results.append(AuditResult(branch=branch, changes=changes))
    return results
