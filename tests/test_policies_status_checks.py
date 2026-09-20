from repo_policy.models import StatusChecksPolicy
from repo_policy.policies import status_checks


def test_to_branch_protection_none_when_empty():
    assert status_checks.to_branch_protection(None) is None
    assert status_checks.to_branch_protection(StatusChecksPolicy(required=[])) is None


def test_to_branch_protection_builds_payload():
    payload = status_checks.to_branch_protection(StatusChecksPolicy(required=["build", "test"]))
    assert payload["contexts"] == ["build", "test"]
    assert payload["checks"] == [
        {"context": "build", "app_id": None},
        {"context": "test", "app_id": None},
    ]


def test_to_branch_protection_defaults_strict_false_when_no_current_state():
    payload = status_checks.to_branch_protection(StatusChecksPolicy(required=["build"]), current=None)
    assert payload["strict"] is False


def test_to_branch_protection_preserves_strict_from_current_state():
    payload = status_checks.to_branch_protection(
        StatusChecksPolicy(required=["build"]), current={"strict": True, "contexts": ["build"]}
    )
    assert payload["strict"] is True


def test_from_branch_protection_none_when_absent():
    assert status_checks.from_branch_protection(None) is None


def test_from_branch_protection_reads_contexts():
    result = status_checks.from_branch_protection({"contexts": ["build"], "checks": []})
    assert result == StatusChecksPolicy(required=["build"])


def test_to_ruleset_rule_none_when_empty():
    assert status_checks.to_ruleset_rule(StatusChecksPolicy(required=[])) is None


def test_to_ruleset_rule_builds_rule():
    rule = status_checks.to_ruleset_rule(StatusChecksPolicy(required=["build"]))
    assert rule["type"] == "required_status_checks"
    assert rule["parameters"]["required_status_checks"] == [{"context": "build"}]


def test_to_ruleset_rule_defaults_strict_false_when_no_current_state():
    rule = status_checks.to_ruleset_rule(StatusChecksPolicy(required=["build"]), current=None)
    assert rule["parameters"]["strict_required_status_checks_policy"] is False


def test_to_ruleset_rule_preserves_strict_from_current_state():
    current_rule = {
        "type": "required_status_checks",
        "parameters": {
            "required_status_checks": [{"context": "build"}],
            "strict_required_status_checks_policy": True,
        },
    }
    rule = status_checks.to_ruleset_rule(StatusChecksPolicy(required=["build"]), current=current_rule)
    assert rule["parameters"]["strict_required_status_checks_policy"] is True


def test_to_ruleset_rule_defaults_do_not_enforce_on_create_false_when_no_current_state():
    rule = status_checks.to_ruleset_rule(StatusChecksPolicy(required=["build"]), current=None)
    assert rule["parameters"]["do_not_enforce_on_create"] is False


def test_to_ruleset_rule_preserves_do_not_enforce_on_create_from_current_state():
    """do_not_enforce_on_create has no modeled field -- a human-enabled 'allow repositories and
    branches to be created if this check would otherwise prevent it' must survive a full rule
    rebuild triggered by an unrelated, modeled field changing."""
    current_rule = {
        "type": "required_status_checks",
        "parameters": {
            "required_status_checks": [{"context": "build"}],
            "strict_required_status_checks_policy": False,
            "do_not_enforce_on_create": True,
        },
    }
    rule = status_checks.to_ruleset_rule(StatusChecksPolicy(required=["build"]), current=current_rule)
    assert rule["parameters"]["do_not_enforce_on_create"] is True


def test_from_ruleset_rule_none_when_absent():
    assert status_checks.from_ruleset_rule(None) is None


def test_from_ruleset_rule_reads_rule():
    rule = {"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "build"}]}}
    result = status_checks.from_ruleset_rule(rule)
    assert result == StatusChecksPolicy(required=["build"])
