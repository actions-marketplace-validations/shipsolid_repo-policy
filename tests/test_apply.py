from unittest.mock import MagicMock

from repo_policy.apply import apply_all, apply_branch, plan_branch, prune_rulesets
from repo_policy.models import BranchPolicy, PolicyConfig, PullRequestPolicy


def _config(**branch_kwargs) -> PolicyConfig:
    return PolicyConfig(version=1, branches={"main": BranchPolicy(**branch_kwargs)})


def test_plan_branch_reports_no_changes_when_already_compliant():
    client = MagicMock()
    client.get_branch_protection.return_value = None
    client.get_required_signatures.return_value = False
    config = _config()  # every field left unset -> managed-scope compares against itself
    changes, _resolved = plan_branch(client, config, "main")
    assert changes == []


def test_apply_branch_skips_api_calls_when_no_changes():
    client = MagicMock()
    client.get_branch_protection.return_value = None
    client.get_required_signatures.return_value = False
    config = _config()
    result = apply_branch(client, config, "main")
    assert result.applied is False
    client.put_branch_protection.assert_not_called()


def test_apply_branch_puts_protection_when_changes_exist():
    client = MagicMock()
    client.get_branch_protection.return_value = None
    client.get_required_signatures.return_value = False
    config = _config(
        pull_requests=PullRequestPolicy(required=True, approvals=2, code_owner_review=True),
        linear_history=True,
    )
    result = apply_branch(client, config, "main")
    assert result.applied is True
    client.put_branch_protection.assert_called_once()
    payload = client.put_branch_protection.call_args.args[1]
    assert payload["required_linear_history"] is True
    assert payload["required_pull_request_reviews"]["required_approving_review_count"] == 2


def test_apply_branch_sets_signed_commits_separately():
    client = MagicMock()
    client.get_branch_protection.return_value = None
    client.get_required_signatures.return_value = False
    config = _config(signed_commits=True)
    apply_branch(client, config, "main")
    client.set_required_signatures.assert_called_once_with("main", True)


def test_apply_branch_creates_ruleset_when_absent():
    client = MagicMock()
    client.find_ruleset_by_name.return_value = None
    config = _config(enforcement="ruleset", linear_history=True)
    result = apply_branch(client, config, "main")
    assert result.applied is True
    client.create_ruleset.assert_called_once()
    client.update_ruleset.assert_not_called()


def test_apply_branch_updates_existing_ruleset():
    client = MagicMock()
    client.find_ruleset_by_name.return_value = {"id": 7, "name": "repo-policy:main", "rules": []}
    config = _config(enforcement="ruleset", linear_history=True)
    result = apply_branch(client, config, "main")
    assert result.applied is True
    client.update_ruleset.assert_called_once()
    assert client.update_ruleset.call_args.args[0] == 7


def test_apply_all_applies_every_declared_branch():
    client = MagicMock()
    client.get_branch_protection.return_value = None
    client.get_required_signatures.return_value = False
    config = PolicyConfig(
        version=1, branches={"main": BranchPolicy(), "release": BranchPolicy(linear_history=True)}
    )
    results = apply_all(client, config)
    assert {r.branch for r in results} == {"main", "release"}


def test_prune_rulesets_deletes_only_orphaned_repo_policy_rulesets():
    client = MagicMock()
    client.list_rulesets.return_value = [
        {"id": 1, "name": "repo-policy:main"},
        {"id": 2, "name": "repo-policy:old-branch"},
        {"id": 3, "name": "someone-elses-ruleset"},
    ]
    config = _config()  # only "main" declared
    deleted = prune_rulesets(client, config)
    assert deleted == ["repo-policy:old-branch"]
    client.delete_ruleset.assert_called_once_with(2)
