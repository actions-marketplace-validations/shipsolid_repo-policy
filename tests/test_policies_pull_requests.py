from repo_policy.models import PullRequestPolicy
from repo_policy.policies import pull_requests


def test_to_branch_protection_none_when_not_required():
    assert pull_requests.to_branch_protection(PullRequestPolicy(required=False)) is None


def test_to_branch_protection_builds_payload():
    policy = PullRequestPolicy(required=True, approvals=2, code_owner_review=True)
    payload = pull_requests.to_branch_protection(policy)
    assert payload["required_approving_review_count"] == 2
    assert payload["require_code_owner_reviews"] is True


def test_from_branch_protection_none_means_not_required():
    result = pull_requests.from_branch_protection(None)
    assert result.required is False
    assert result.approvals == 0


def test_from_branch_protection_reads_payload():
    data = {"required_approving_review_count": 3, "require_code_owner_reviews": True}
    result = pull_requests.from_branch_protection(data)
    assert result == PullRequestPolicy(required=True, approvals=3, code_owner_review=True)


def test_to_ruleset_rule_none_when_not_required():
    assert pull_requests.to_ruleset_rule(PullRequestPolicy(required=False)) is None


def test_to_ruleset_rule_builds_rule():
    policy = PullRequestPolicy(required=True, approvals=1, code_owner_review=False)
    rule = pull_requests.to_ruleset_rule(policy)
    assert rule["type"] == "pull_request"
    assert rule["parameters"]["required_approving_review_count"] == 1


def test_from_ruleset_rule_none_means_not_required():
    result = pull_requests.from_ruleset_rule(None)
    assert result.required is False


def test_from_ruleset_rule_reads_rule():
    rule = {
        "type": "pull_request",
        "parameters": {"required_approving_review_count": 2, "require_code_owner_review": True},
    }
    result = pull_requests.from_ruleset_rule(rule)
    assert result == PullRequestPolicy(required=True, approvals=2, code_owner_review=True)
