from unittest.mock import patch

from click.testing import CliRunner

from repo_policy.cli import main


def test_validate_exits_0_on_valid_config():
    runner = CliRunner()
    result = runner.invoke(main, ["validate", "--config", "tests/fixtures/policy_valid.yml"])
    assert result.exit_code == 0
    assert "is valid" in result.output


def test_validate_exits_2_on_invalid_config():
    runner = CliRunner()
    result = runner.invoke(main, ["validate", "--config", "tests/fixtures/policy_invalid.yml"])
    assert result.exit_code == 2


def test_validate_exits_2_on_missing_config():
    runner = CliRunner()
    result = runner.invoke(main, ["validate", "--config", "tests/fixtures/nope.yml"])
    assert result.exit_code == 2


@patch("repo_policy.cli.GitHubClient")
def test_audit_exits_0_when_compliant(mock_client_cls):
    mock_client = mock_client_cls.return_value.__enter__.return_value
    mock_client.get_branch_protection.return_value = None
    mock_client.get_required_signatures.return_value = False
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "audit",
            "--config", "tests/fixtures/policy_no_requirements.yml",
            "--repo", "acme/widgets",
            "--token", "t",
        ],
    )
    assert result.exit_code == 0
    assert "is compliant" in result.output


@patch("repo_policy.cli.GitHubClient")
def test_audit_exits_1_on_drift(mock_client_cls):
    mock_client = mock_client_cls.return_value.__enter__.return_value
    mock_client.get_branch_protection.return_value = None
    mock_client.get_required_signatures.return_value = False
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["audit", "--config", "tests/fixtures/policy_valid.yml", "--repo", "acme/widgets", "--token", "t"],
    )
    assert result.exit_code == 1


@patch("repo_policy.cli.GitHubClient")
def test_plan_renders_diff_and_exits_1_on_drift(mock_client_cls):
    mock_client = mock_client_cls.return_value.__enter__.return_value
    mock_client.get_branch_protection.return_value = None
    mock_client.get_required_signatures.return_value = False
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["plan", "--config", "tests/fixtures/policy_valid.yml", "--repo", "acme/widgets", "--token", "t"],
    )
    assert result.exit_code == 1
    assert "Repository: acme/widgets" in result.output


@patch("repo_policy.cli.GitHubClient")
def test_apply_exits_0_and_applies_changes(mock_client_cls):
    mock_client = mock_client_cls.return_value.__enter__.return_value
    mock_client.get_branch_protection.return_value = None
    mock_client.get_required_signatures.return_value = False
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["apply", "--config", "tests/fixtures/policy_valid.yml", "--repo", "acme/widgets", "--token", "t"],
    )
    assert result.exit_code == 0
    mock_client.put_branch_protection.assert_called_once()


@patch("repo_policy.cli.GitHubClient")
def test_audit_reports_usage_error_when_repo_cannot_be_resolved(mock_client_cls, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    (tmp_path / "policy.yml").write_text("version: 1\nbranches:\n  main: {}\n")
    runner = CliRunner()
    result = runner.invoke(main, ["audit", "--token", "t"])
    assert result.exit_code != 0
    mock_client_cls.assert_not_called()
