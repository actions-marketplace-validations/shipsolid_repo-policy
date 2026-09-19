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


def test_load_policy_gives_actionable_message_when_top_level_is_not_a_mapping(tmp_path):
    config_path = tmp_path / "policy.yml"
    config_path.write_text("- not\n- a\n- mapping\n")
    with pytest.raises(ConfigError) as exc_info:
        load_policy(config_path)
    assert "<policy file root>" in str(exc_info.value)


def test_load_policy_does_not_coerce_yaml_1_1_bareword_branch_names_to_booleans(tmp_path):
    """PyYAML's SafeLoader resolves bare yes/no/on/off (any casing) to Python booleans by
    default (YAML 1.1's "Norway problem") -- a branch literally named `no` would otherwise
    silently become the dict key False before pydantic ever sees it."""
    config_path = tmp_path / "policy.yml"
    config_path.write_text("version: 1\nbranches:\n  no:\n    linear_history: true\n")
    config = load_policy(config_path)
    assert "no" in config.branches
    assert config.branches["no"].linear_history is True


def test_load_policy_still_parses_true_false_as_booleans(tmp_path):
    config_path = tmp_path / "policy.yml"
    config_path.write_text("version: 1\nbranches:\n  main:\n    linear_history: true\n    signed_commits: false\n")
    config = load_policy(config_path)
    assert config.branches["main"].linear_history is True
    assert config.branches["main"].signed_commits is False
