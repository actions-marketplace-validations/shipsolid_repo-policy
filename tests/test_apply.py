from unittest.mock import MagicMock

from repo_policy.apply import (
    apply_all,
    apply_branch,
    detect_stale_branch_protection,
    plan_branch,
    prune_rulesets,
)
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
    config = _config(enforcement="ruleset")  # only "main" declared, still under enforcement: ruleset
    deleted = prune_rulesets(client, config)
    assert deleted == ["repo-policy:old-branch"]
    client.delete_ruleset.assert_called_once_with(2)


def test_prune_rulesets_deletes_ruleset_for_branch_switched_to_branch_protection():
    """main is still declared in policy.yml, but its enforcement changed from ruleset to
    branch_protection -- the old repo-policy:main ruleset is now an orphan and must be pruned,
    the same as if main had been removed from policy.yml entirely."""
    client = MagicMock()
    client.list_rulesets.return_value = [{"id": 1, "name": "repo-policy:main"}]
    config = _config(enforcement="branch_protection")  # only "main" declared, now branch_protection
    deleted = prune_rulesets(client, config)
    assert deleted == ["repo-policy:main"]
    client.delete_ruleset.assert_called_once_with(1)


def test_detect_stale_branch_protection_flags_ruleset_branch_with_leftover_protection():
    client = MagicMock()
    client.get_branch_protection.return_value = {"enforce_admins": {"enabled": True}}
    config = _config(enforcement="ruleset")
    assert detect_stale_branch_protection(client, config) == ["main"]


def test_detect_stale_branch_protection_ignores_branch_protection_enforced_branches():
    client = MagicMock()
    config = _config(enforcement="branch_protection")
    assert detect_stale_branch_protection(client, config) == []
    client.get_branch_protection.assert_not_called()


def test_detect_stale_branch_protection_empty_when_no_leftover_protection_exists():
    client = MagicMock()
    client.get_branch_protection.return_value = None
    config = _config(enforcement="ruleset")
    assert detect_stale_branch_protection(client, config) == []


def test_apply_branch_flags_stale_branch_protection_for_ruleset_enforced_branch():
    client = MagicMock()
    client.find_ruleset_by_name.return_value = None
    client.get_branch_protection.return_value = {"enforce_admins": {"enabled": True}}
    config = _config(enforcement="ruleset", linear_history=True)
    result = apply_branch(client, config, "main")
    assert result.stale_branch_protection is True


def test_apply_branch_no_stale_flag_for_branch_protection_enforced_branch():
    client = MagicMock()
    client.get_branch_protection.return_value = None
    client.get_required_signatures.return_value = False
    config = _config()  # enforcement: branch_protection (the default)
    result = apply_branch(client, config, "main")
    assert result.stale_branch_protection is False


def test_prune_rulesets_reuses_a_prefetched_list_without_a_new_call():
    client = MagicMock()
    prefetched = [{"id": 2, "name": "repo-policy:old-branch"}]
    config = _config()  # only "main" declared
    deleted = prune_rulesets(client, config, rulesets_cache=prefetched)
    assert deleted == ["repo-policy:old-branch"]
    client.list_rulesets.assert_not_called()


def test_apply_all_fetches_ruleset_list_at_most_once_for_multiple_ruleset_branches():
    client = MagicMock()
    client.list_rulesets.return_value = []
    client.find_ruleset_by_name.return_value = None
    config = PolicyConfig(
        version=1,
        branches={
            "main": BranchPolicy(enforcement="ruleset", linear_history=True),
            "release": BranchPolicy(enforcement="ruleset", linear_history=True),
        },
    )
    apply_all(client, config)
    assert client.list_rulesets.call_count == 1


def test_apply_all_skips_ruleset_prefetch_when_no_branch_uses_it():
    client = MagicMock()
    client.get_branch_protection.return_value = None
    client.get_required_signatures.return_value = False
    config = _config()  # branch_protection (the default), not ruleset
    apply_all(client, config)
    client.list_rulesets.assert_not_called()
