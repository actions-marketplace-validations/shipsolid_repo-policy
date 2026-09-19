from __future__ import annotations

from dataclasses import dataclass

from repo_policy.apply import plan_branch
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
    results = []
    for branch in config.branches:
        changes, _resolved = plan_branch(client, config, branch)
        results.append(AuditResult(branch=branch, changes=changes))
    return results
