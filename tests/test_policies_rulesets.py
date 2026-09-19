from repo_policy.models import BranchPolicy, PullRequestPolicy, StatusChecksPolicy
from repo_policy.policies import rulesets


def test_ruleset_name_is_deterministic():
    assert rulesets.ruleset_name("main") == "repo-policy:main"


def test_from_api_none_means_fully_permissive():
    result = rulesets.from_api(None)
    assert result.pull_requests == PullRequestPolicy(required=False, approvals=0, code_owner_review=False)
    assert result.status_checks is None
    assert result.signed_commits is False
    assert result.linear_history is False
    assert result.allow_force_push is True
    assert result.allow_deletion is True


def test_from_api_reads_rules_array():
    data = {
        "rules": [
            {"type": "pull_request", "parameters": {"required_approving_review_count": 1, "require_code_owner_review": False}},
            {"type": "required_signatures"},
            {"type": "non_fast_forward"},
        ]
    }
    result = rulesets.from_api(data)
    assert result.pull_requests == PullRequestPolicy(required=True, approvals=1, code_owner_review=False)
    assert result.signed_commits is True
    assert result.linear_history is False
    assert result.allow_force_push is False
    assert result.allow_deletion is True


def test_to_api_payload_builds_ruleset_targeting_branch():
    resolved = BranchPolicy(
        pull_requests=PullRequestPolicy(required=True, approvals=2, code_owner_review=True),
        status_checks=StatusChecksPolicy(required=["build"]),
        signed_commits=True,
        linear_history=True,
        allow_force_push=False,
        allow_deletion=False,
    )
    payload = rulesets.to_api_payload("main", resolved)
    assert payload["name"] == "repo-policy:main"
    assert payload["target"] == "branch"
    assert payload["enforcement"] == "active"
    assert payload["conditions"]["ref_name"]["include"] == ["refs/heads/main"]
    rule_types = {rule["type"] for rule in payload["rules"]}
    assert rule_types == {
        "pull_request",
        "required_status_checks",
        "required_signatures",
        "required_linear_history",
        "non_fast_forward",
        "deletion",
    }


def test_to_api_payload_omits_rules_for_permissive_fields():
    resolved = BranchPolicy(
        pull_requests=PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
        status_checks=None,
        signed_commits=False,
        linear_history=False,
        allow_force_push=True,
        allow_deletion=True,
    )
    payload = rulesets.to_api_payload("main", resolved)
    assert payload["rules"] == []
