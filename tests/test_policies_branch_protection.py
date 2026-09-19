from repo_policy.models import BranchPolicy, PullRequestPolicy, StatusChecksPolicy
from repo_policy.policies import branch_protection


def test_from_api_none_means_fully_permissive():
    result = branch_protection.from_api(None, signed_commits=False)
    assert result.pull_requests == PullRequestPolicy(required=False, approvals=0, code_owner_review=False)
    assert result.status_checks is None
    assert result.signed_commits is False
    assert result.linear_history is False
    assert result.allow_force_push is True
    assert result.allow_deletion is True


def test_from_api_reads_wrapped_booleans():
    data = {
        "required_pull_request_reviews": {"required_approving_review_count": 2, "require_code_owner_reviews": True},
        "required_status_checks": {"contexts": ["build"], "checks": []},
        "required_linear_history": {"enabled": True},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
    }
    result = branch_protection.from_api(data, signed_commits=True)
    assert result.pull_requests == PullRequestPolicy(required=True, approvals=2, code_owner_review=True)
    assert result.status_checks == StatusChecksPolicy(required=["build"])
    assert result.linear_history is True
    assert result.allow_force_push is False
    assert result.allow_deletion is False
    assert result.signed_commits is True


def test_to_api_payload_builds_full_replace_body():
    resolved = BranchPolicy(
        pull_requests=PullRequestPolicy(required=True, approvals=2, code_owner_review=True),
        status_checks=StatusChecksPolicy(required=["build"]),
        linear_history=True,
        allow_force_push=False,
        allow_deletion=False,
    )
    payload = branch_protection.to_api_payload(resolved, current_raw=None)
    assert payload["enforce_admins"] is False
    assert payload["restrictions"] is None
    assert payload["required_pull_request_reviews"]["required_approving_review_count"] == 2
    assert payload["required_status_checks"]["contexts"] == ["build"]
    assert payload["required_linear_history"] is True
    assert payload["allow_force_pushes"] is False
    assert payload["allow_deletions"] is False


def test_to_api_payload_preserves_unmodeled_current_fields():
    current_raw = {
        "enforce_admins": {"enabled": True},
        "restrictions": {"users": ["octocat"], "teams": []},
    }
    resolved = BranchPolicy(
        pull_requests=PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
        linear_history=False,
        allow_force_push=True,
        allow_deletion=True,
    )
    payload = branch_protection.to_api_payload(resolved, current_raw=current_raw)
    assert payload["enforce_admins"] is True
    assert payload["restrictions"] == {"users": ["octocat"], "teams": []}
