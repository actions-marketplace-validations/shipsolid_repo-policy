import pytest
from pydantic import ValidationError

from repo_policy.models import (
    _RULESET_UNSUPPORTED_FIELDS,
    FIELD_SPECS,
    PERMISSIVE_PULL_REQUESTS,
    BranchPolicy,
    PolicyConfig,
    PullRequestPolicy,
    RepoSettingsPolicy,
    StatusChecksPolicy,
    effective_strict,
    permissive_branch_policy,
)


def test_branch_policy_defaults():
    policy = BranchPolicy()
    assert policy.enforcement == "branch_protection"
    assert policy.strict is None
    assert policy.pull_requests is None


def test_branch_policy_rejects_unknown_enforcement():
    with pytest.raises(ValidationError):
        BranchPolicy(enforcement="bogus")


def test_branch_policy_rejects_enforce_admins_under_ruleset():
    with pytest.raises(ValidationError, match="enforce_admins"):
        BranchPolicy(enforcement="ruleset", enforce_admins=True)


def test_branch_policy_allows_enforce_admins_under_branch_protection():
    policy = BranchPolicy(enforcement="branch_protection", enforce_admins=True)
    assert policy.enforce_admins is True


def test_branch_policy_allows_ruleset_enforcement_when_enforce_admins_unset():
    policy = BranchPolicy(enforcement="ruleset")
    assert policy.enforce_admins is None


def test_branch_policy_rejects_required_conversation_resolution_under_ruleset():
    with pytest.raises(ValidationError, match="required_conversation_resolution"):
        BranchPolicy(enforcement="ruleset", required_conversation_resolution=True)


def test_branch_policy_allows_required_conversation_resolution_under_branch_protection():
    policy = BranchPolicy(enforcement="branch_protection", required_conversation_resolution=True)
    assert policy.required_conversation_resolution is True


def test_branch_policy_rejects_lock_branch_under_ruleset():
    with pytest.raises(ValidationError, match="lock_branch"):
        BranchPolicy(enforcement="ruleset", lock_branch=True)


def test_branch_policy_allows_lock_branch_under_branch_protection():
    policy = BranchPolicy(enforcement="branch_protection", lock_branch=True)
    assert policy.lock_branch is True


def test_branch_policy_rejects_allow_fork_syncing_under_ruleset():
    with pytest.raises(ValidationError, match="allow_fork_syncing"):
        BranchPolicy(enforcement="ruleset", allow_fork_syncing=True)


def test_branch_policy_allows_allow_fork_syncing_under_branch_protection():
    policy = BranchPolicy(enforcement="branch_protection", allow_fork_syncing=False)
    assert policy.allow_fork_syncing is False


def test_branch_policy_rejects_allow_fork_syncing_true_without_lock_branch():
    with pytest.raises(ValidationError, match="lock_branch"):
        BranchPolicy(enforcement="branch_protection", allow_fork_syncing=True)


def test_branch_policy_rejects_allow_fork_syncing_true_with_lock_branch_false():
    with pytest.raises(ValidationError, match="lock_branch"):
        BranchPolicy(enforcement="branch_protection", allow_fork_syncing=True, lock_branch=False)


def test_branch_policy_allows_allow_fork_syncing_true_with_lock_branch_true():
    policy = BranchPolicy(enforcement="branch_protection", allow_fork_syncing=True, lock_branch=True)
    assert policy.allow_fork_syncing is True
    assert policy.lock_branch is True


def test_branch_policy_rejects_clear_restrictions_under_ruleset():
    with pytest.raises(ValidationError, match="clear_restrictions"):
        BranchPolicy(enforcement="ruleset", clear_restrictions=False)


def test_branch_policy_allows_clear_restrictions_under_branch_protection():
    policy = BranchPolicy(enforcement="branch_protection", clear_restrictions=True)
    assert policy.clear_restrictions is True


def test_policy_config_parses_nested_branches():
    config = PolicyConfig(
        version=1,
        branches={
            "main": BranchPolicy(
                pull_requests=PullRequestPolicy(required=True, approvals=2, code_owner_review=True),
                status_checks=StatusChecksPolicy(required=["build", "test"]),
                linear_history=True,
            )
        },
    )
    assert config.branches["main"].pull_requests.approvals == 2
    assert config.branches["main"].status_checks.required == ["build", "test"]


def test_policy_config_rejects_unsupported_version():
    with pytest.raises(ValidationError):
        PolicyConfig(version=2, branches={})


def test_effective_strict_falls_back_to_top_level_default():
    config = PolicyConfig(version=1, strict=True, branches={"main": BranchPolicy()})
    assert effective_strict(config, "main") is True


def test_effective_strict_branch_override_wins():
    config = PolicyConfig(version=1, strict=True, branches={"main": BranchPolicy(strict=False)})
    assert effective_strict(config, "main") is False


def test_repo_settings_policy_defaults_to_all_unset():
    policy = RepoSettingsPolicy()
    assert policy.delete_branch_on_merge is None
    assert policy.allow_update_branch is None


def test_policy_config_repo_settings_defaults_to_none():
    config = PolicyConfig(version=1, branches={})
    assert config.repo_settings is None


def test_policy_config_parses_repo_settings():
    config = PolicyConfig(
        version=1, branches={},
        repo_settings=RepoSettingsPolicy(delete_branch_on_merge=True, allow_update_branch=False),
    )
    assert config.repo_settings.delete_branch_on_merge is True
    assert config.repo_settings.allow_update_branch is False


def test_repo_settings_rejects_automated_security_fixes_without_vulnerability_alerts():
    with pytest.raises(ValidationError, match="vulnerability_alerts"):
        RepoSettingsPolicy(automated_security_fixes=True)


def test_repo_settings_rejects_automated_security_fixes_with_vulnerability_alerts_false():
    with pytest.raises(ValidationError, match="vulnerability_alerts"):
        RepoSettingsPolicy(automated_security_fixes=True, vulnerability_alerts=False)


def test_repo_settings_allows_automated_security_fixes_with_vulnerability_alerts_true():
    policy = RepoSettingsPolicy(automated_security_fixes=True, vulnerability_alerts=True)
    assert policy.automated_security_fixes is True


def test_repo_settings_rejects_secret_scanning_push_protection_without_secret_scanning():
    with pytest.raises(ValidationError, match="secret_scanning"):
        RepoSettingsPolicy(secret_scanning_push_protection=True)


def test_repo_settings_rejects_secret_scanning_push_protection_with_secret_scanning_false():
    with pytest.raises(ValidationError, match="secret_scanning"):
        RepoSettingsPolicy(secret_scanning_push_protection=True, secret_scanning=False)


def test_repo_settings_allows_secret_scanning_push_protection_with_secret_scanning_true():
    policy = RepoSettingsPolicy(secret_scanning_push_protection=True, secret_scanning=True)
    assert policy.secret_scanning_push_protection is True


def test_field_specs_cover_every_diffable_field():
    names = [spec.name for spec in FIELD_SPECS]
    assert names == [
        "pull_requests", "status_checks", "signed_commits", "linear_history",
        "allow_force_push", "allow_deletion", "enforce_admins",
        "required_conversation_resolution", "lock_branch", "allow_fork_syncing",
        "clear_restrictions",
    ]


def test_field_specs_permissive_pull_requests_matches_constant():
    spec = next(s for s in FIELD_SPECS if s.name == "pull_requests")
    assert spec.default == PERMISSIVE_PULL_REQUESTS


def test_ruleset_unsupported_fields_derived_from_field_specs():
    expected = {spec.name: spec.default for spec in FIELD_SPECS if not spec.ruleset_supported}
    assert _RULESET_UNSUPPORTED_FIELDS == expected
    assert set(_RULESET_UNSUPPORTED_FIELDS) == {
        "enforce_admins", "required_conversation_resolution", "lock_branch",
        "allow_fork_syncing", "clear_restrictions",
    }


def test_field_specs_inverted_fields():
    inverted = {spec.name for spec in FIELD_SPECS if spec.inverted}
    assert inverted == {"allow_force_push", "allow_deletion", "clear_restrictions"}


def test_permissive_branch_policy_branch_protection():
    policy = permissive_branch_policy("branch_protection", signed_commits=True)
    assert policy.enforcement == "branch_protection"
    assert policy.signed_commits is True
    assert policy.pull_requests == PERMISSIVE_PULL_REQUESTS
    assert policy.status_checks is None
    assert policy.clear_restrictions is True
    assert policy.enforce_admins is False


def test_permissive_branch_policy_ruleset_defaults_signed_commits_false():
    policy = permissive_branch_policy("ruleset")
    assert policy.enforcement == "ruleset"
    assert policy.signed_commits is False
