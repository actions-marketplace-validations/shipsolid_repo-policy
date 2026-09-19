from repo_policy.models import RepoSettingsPolicy
from repo_policy.policies import repo_settings


def test_diff_flat_settings_detects_change():
    current_repo = {"delete_branch_on_merge": False, "allow_update_branch": True}
    desired = RepoSettingsPolicy(delete_branch_on_merge=True)
    changes = repo_settings.diff_flat_settings(current_repo, desired)
    assert len(changes) == 1
    assert changes[0].field == "delete_branch_on_merge"
    assert changes[0].current_value is False
    assert changes[0].desired_value is True
    assert changes[0].action == "add"


def test_diff_flat_settings_skips_undeclared_fields():
    current_repo = {"delete_branch_on_merge": False, "allow_update_branch": False}
    desired = RepoSettingsPolicy(delete_branch_on_merge=True)  # allow_update_branch left unset
    changes = repo_settings.diff_flat_settings(current_repo, desired)
    assert len(changes) == 1
    assert changes[0].field == "delete_branch_on_merge"


def test_diff_flat_settings_empty_when_already_compliant():
    current_repo = {"delete_branch_on_merge": True, "allow_update_branch": True}
    desired = RepoSettingsPolicy(delete_branch_on_merge=True, allow_update_branch=True)
    assert repo_settings.diff_flat_settings(current_repo, desired) == []


def test_to_flat_settings_payload_builds_dict_from_changes():
    current_repo = {"delete_branch_on_merge": False, "allow_update_branch": False}
    desired = RepoSettingsPolicy(delete_branch_on_merge=True, allow_update_branch=True)
    changes = repo_settings.diff_flat_settings(current_repo, desired)
    payload = repo_settings.to_flat_settings_payload(changes)
    assert payload == {"delete_branch_on_merge": True, "allow_update_branch": True}


def test_diff_security_and_analysis_detects_change():
    current_repo = {"security_and_analysis": {"secret_scanning": {"status": "disabled"}}}
    desired = RepoSettingsPolicy(secret_scanning=True)
    changes = repo_settings.diff_security_and_analysis(current_repo, desired)
    assert len(changes) == 1
    assert changes[0].field == "secret_scanning"
    assert changes[0].action == "add"


def test_diff_security_and_analysis_treats_absent_block_as_disabled():
    current_repo = {}  # no security_and_analysis key at all
    desired = RepoSettingsPolicy(secret_scanning=True)
    changes = repo_settings.diff_security_and_analysis(current_repo, desired)
    assert len(changes) == 1
    assert changes[0].current_value is False


def test_to_security_and_analysis_payload_builds_status_wrapped_dict():
    current_repo = {
        "security_and_analysis": {"secret_scanning_push_protection": {"status": "enabled"}}
    }
    desired = RepoSettingsPolicy(secret_scanning=True, secret_scanning_push_protection=False)
    changes = repo_settings.diff_security_and_analysis(current_repo, desired)
    payload = repo_settings.to_security_and_analysis_payload(changes)
    assert payload == {
        "secret_scanning": {"status": "enabled"},
        "secret_scanning_push_protection": {"status": "disabled"},
    }


def test_diff_toggle_returns_change_when_different():
    changes = repo_settings.diff_toggle("vulnerability_alerts", False, True)
    assert len(changes) == 1
    assert changes[0].action == "add"


def test_diff_toggle_empty_when_equal():
    assert repo_settings.diff_toggle("vulnerability_alerts", True, True) == []


def test_diff_toggle_empty_when_current_is_none():
    """current_value=None means 'unavailable' -- never produces a Change."""
    assert repo_settings.diff_toggle("private_vulnerability_reporting", None, True) == []


def test_diff_toggle_empty_when_desired_is_none():
    assert repo_settings.diff_toggle("vulnerability_alerts", False, None) == []
