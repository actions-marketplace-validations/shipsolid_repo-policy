from unittest.mock import MagicMock

from repo_policy.audit import audit_all
from repo_policy.models import BranchPolicy, PolicyConfig, PullRequestPolicy


def test_audit_all_reports_compliant_when_no_drift():
    client = MagicMock()
    client.get_branch_protection.return_value = None
    client.get_required_signatures.return_value = False
    config = PolicyConfig(version=1, branches={"main": BranchPolicy()})
    results = audit_all(client, config)
    assert len(results) == 1
    assert results[0].compliant is True
    assert results[0].changes == []


def test_audit_all_reports_drift():
    client = MagicMock()
    client.get_branch_protection.return_value = None
    client.get_required_signatures.return_value = False
    config = PolicyConfig(
        version=1,
        branches={"main": BranchPolicy(pull_requests=PullRequestPolicy(required=True, approvals=1, code_owner_review=False))},
    )
    results = audit_all(client, config)
    assert results[0].compliant is False
    assert len(results[0].changes) == 1


def test_audit_all_covers_every_declared_branch():
    client = MagicMock()
    client.get_branch_protection.return_value = None
    client.get_required_signatures.return_value = False
    config = PolicyConfig(version=1, branches={"main": BranchPolicy(), "release": BranchPolicy()})
    results = audit_all(client, config)
    assert {r.branch for r in results} == {"main", "release"}


def test_audit_all_fetches_ruleset_list_at_most_once_for_multiple_ruleset_branches():
    client = MagicMock()
    client.list_rulesets.return_value = []
    client.find_ruleset_by_name.return_value = None
    config = PolicyConfig(
        version=1,
        branches={
            "main": BranchPolicy(enforcement="ruleset"),
            "release": BranchPolicy(enforcement="ruleset"),
        },
    )
    audit_all(client, config)
    assert client.list_rulesets.call_count == 1
