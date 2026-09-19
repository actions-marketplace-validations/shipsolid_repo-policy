import sys
from unittest.mock import patch

import pytest

from repo_policy.entrypoint import run


@patch("repo_policy.entrypoint.main")
def test_run_uses_default_config_and_mode_when_unset(mock_main, monkeypatch):
    monkeypatch.delenv("INPUT_CONFIG", raising=False)
    monkeypatch.delenv("INPUT_MODE", raising=False)
    run()
    assert sys.argv == ["repo-policy", "audit", "--config", ".github/repository-policy.yml"]


@patch("repo_policy.entrypoint.main")
def test_run_uses_default_config_when_input_config_is_empty_string(mock_main, monkeypatch):
    monkeypatch.setenv("INPUT_CONFIG", "")
    monkeypatch.delenv("INPUT_MODE", raising=False)
    run()
    assert sys.argv == ["repo-policy", "audit", "--config", ".github/repository-policy.yml"]


@patch("repo_policy.entrypoint.main")
def test_run_uses_default_mode_when_input_mode_is_empty_string(mock_main, monkeypatch):
    monkeypatch.delenv("INPUT_CONFIG", raising=False)
    monkeypatch.setenv("INPUT_MODE", "")
    run()
    assert sys.argv[1] == "audit"


@patch("repo_policy.entrypoint.main")
def test_run_forwards_custom_config_and_mode(mock_main, monkeypatch):
    monkeypatch.setenv("INPUT_CONFIG", "custom.yml")
    monkeypatch.setenv("INPUT_MODE", "apply")
    run()
    assert sys.argv == ["repo-policy", "apply", "--config", "custom.yml"]


def test_run_exits_2_on_unsupported_mode(monkeypatch):
    monkeypatch.setenv("INPUT_MODE", "bogus")
    with pytest.raises(SystemExit) as exc_info:
        run()
    assert exc_info.value.code == 2
