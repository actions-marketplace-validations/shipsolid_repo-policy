import pytest

from repo_policy.config import ConfigError, load_policy


def test_load_policy_parses_valid_file():
    config = load_policy("tests/fixtures/policy_valid.yml")
    assert config.version == 1
    assert config.branches["main"].pull_requests.approvals == 2


def test_load_policy_raises_on_missing_file():
    with pytest.raises(ConfigError, match="not found"):
        load_policy("tests/fixtures/does_not_exist.yml")


def test_load_policy_raises_with_field_context_on_invalid_file():
    with pytest.raises(ConfigError, match="branches.main.enforcement"):
        load_policy("tests/fixtures/policy_invalid.yml")


def test_load_policy_raises_on_empty_file(tmp_path):
    empty = tmp_path / "empty.yml"
    empty.write_text("")
    with pytest.raises(ConfigError, match="empty"):
        load_policy(empty)
