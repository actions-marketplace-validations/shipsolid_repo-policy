from __future__ import annotations

import pytest
from click.testing import CliRunner

from repo_policy.cli import main

from .conftest import LIVE_REPO

pytestmark = pytest.mark.e2e

FULL_POLICY = "tests/e2e/fixtures/e2e_full_policy.yml"
PRUNE_POLICY = "tests/e2e/fixtures/e2e_prune_policy.yml"


def _invoke(*args: str):
    return CliRunner().invoke(main, list(args))


def test_validate_accepts_e2e_fixture_policies():
    for config in (FULL_POLICY, PRUNE_POLICY):
        result = _invoke("validate", "--config", config)
        assert result.exit_code == 0, result.output


def test_live_token_and_repo_are_reachable(live_client):
    repo = live_client.get_repo()
    assert repo["full_name"] == LIVE_REPO
