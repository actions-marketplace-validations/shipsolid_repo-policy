import pytest
from pydantic import ValidationError

from repo_policy.models import (
    BranchPolicy,
    PolicyConfig,
    PullRequestPolicy,
    StatusChecksPolicy,
    effective_strict,
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
