from unittest.mock import MagicMock

from repo_policy.models import PolicyConfig, RepoSettingsPolicy
from repo_policy.repo_settings import apply_repo_settings, plan_repo_settings


def test_plan_repo_settings_returns_empty_result_when_section_absent():
    client = MagicMock()
    config = PolicyConfig(version=1, branches={})  # no repo_settings declared
    result = plan_repo_settings(client, config)
    assert result.changes == []
    assert result.unavailable == []
    client.get_repo.assert_not_called()


def test_plan_repo_settings_detects_flat_setting_drift():
    client = MagicMock()
    client.get_repo.return_value = {"delete_branch_on_merge": False}
    config = PolicyConfig(
        version=1, branches={}, repo_settings=RepoSettingsPolicy(delete_branch_on_merge=True)
    )
    result = plan_repo_settings(client, config)
    assert len(result.changes) == 1
    assert result.changes[0].field == "delete_branch_on_merge"


def test_apply_repo_settings_calls_update_when_drift_exists():
    client = MagicMock()
    client.get_repo.return_value = {"delete_branch_on_merge": False}
    config = PolicyConfig(
        version=1, branches={}, repo_settings=RepoSettingsPolicy(delete_branch_on_merge=True)
    )
    result = apply_repo_settings(client, config)
    assert result.applied is True
    client.update_repo_settings.assert_called_once_with({"delete_branch_on_merge": True})


def test_apply_repo_settings_is_idempotent_when_already_compliant():
    client = MagicMock()
    client.get_repo.return_value = {"delete_branch_on_merge": True}
    config = PolicyConfig(
        version=1, branches={}, repo_settings=RepoSettingsPolicy(delete_branch_on_merge=True)
    )
    result = apply_repo_settings(client, config)
    assert result.applied is False
    client.update_repo_settings.assert_not_called()


def test_plan_repo_settings_detects_vulnerability_alerts_drift():
    client = MagicMock()
    client.get_repo.return_value = {}
    client.get_vulnerability_alerts.return_value = False
    config = PolicyConfig(version=1, branches={}, repo_settings=RepoSettingsPolicy(vulnerability_alerts=True))
    result = plan_repo_settings(client, config)
    assert len(result.changes) == 1
    assert result.changes[0].field == "vulnerability_alerts"


def test_apply_repo_settings_enables_vulnerability_alerts():
    client = MagicMock()
    client.get_repo.return_value = {}
    client.get_vulnerability_alerts.return_value = False
    config = PolicyConfig(version=1, branches={}, repo_settings=RepoSettingsPolicy(vulnerability_alerts=True))
    result = apply_repo_settings(client, config)
    assert result.applied is True
    client.enable_vulnerability_alerts.assert_called_once()


def test_apply_repo_settings_enables_alerts_before_security_fixes():
    """Both fields are drifted in the same apply -- vulnerability_alerts must be enabled first,
    since GitHub rejects enabling automated_security_fixes before it."""
    call_order = []
    client = MagicMock()
    client.get_repo.return_value = {}
    client.get_vulnerability_alerts.return_value = False
    client.get_automated_security_fixes.return_value = False
    client.enable_vulnerability_alerts.side_effect = lambda: call_order.append("vulnerability_alerts")
    client.enable_automated_security_fixes.side_effect = lambda: call_order.append("automated_security_fixes")
    config = PolicyConfig(
        version=1, branches={},
        repo_settings=RepoSettingsPolicy(vulnerability_alerts=True, automated_security_fixes=True),
    )
    apply_repo_settings(client, config)
    assert call_order == ["vulnerability_alerts", "automated_security_fixes"]
