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
def test_apply_strict_mode_shares_one_ruleset_fetch_between_apply_and_prune(mock_client_cls):
    mock_client = mock_client_cls.return_value.__enter__.return_value
    mock_client.get_branch_protection.return_value = None
    mock_client.get_required_signatures.return_value = False
    mock_client.list_rulesets.return_value = [{"id": 9, "name": "repo-policy:removed-branch"}]
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["apply", "--config", "tests/fixtures/policy_strict.yml", "--repo", "acme/widgets", "--token", "t"],
    )
    assert result.exit_code == 0
    assert mock_client.list_rulesets.call_count == 1
    mock_client.delete_ruleset.assert_called_once_with(9)
    assert "removed orphaned ruleset repo-policy:removed-branch" in result.output


@patch("repo_policy.cli.GitHubClient")
def test_audit_reports_usage_error_on_malformed_repo(mock_client_cls):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["audit", "--config", "tests/fixtures/policy_no_requirements.yml", "--repo", "widgets", "--token", "t"],
    )
    assert result.exit_code != 0
    assert "invalid repository" in result.output
    mock_client_cls.assert_not_called()


@patch("repo_policy.cli.GitHubClient")
def test_audit_reports_usage_error_when_repo_cannot_be_resolved(mock_client_cls, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    (tmp_path / "policy.yml").write_text("version: 1\nbranches:\n  main: {}\n")
    runner = CliRunner()
    result = runner.invoke(main, ["audit", "--token", "t"])
    assert result.exit_code != 0
    mock_client_cls.assert_not_called()


@patch("repo_policy.cli.GitHubClient")
def test_audit_reports_usage_error_when_no_token_configured(mock_client_cls, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["audit", "--config", "tests/fixtures/policy_no_requirements.yml", "--repo", "acme/widgets"],
    )
    assert result.exit_code != 0
    assert "no GitHub token" in result.output
    mock_client_cls.assert_not_called()


@patch("repo_policy.cli.subprocess.run", side_effect=FileNotFoundError("git not found"))
@patch("repo_policy.cli.GitHubClient")
def test_audit_reports_usage_error_when_git_binary_is_missing(mock_client_cls, mock_run, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    (tmp_path / "policy.yml").write_text("version: 1\nbranches:\n  main: {}\n")
    runner = CliRunner()
    result = runner.invoke(main, ["audit", "--token", "t"])
    assert result.exit_code != 0
    assert "could not determine repository" in result.output
    mock_client_cls.assert_not_called()
