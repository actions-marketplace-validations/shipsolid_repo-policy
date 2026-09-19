from __future__ import annotations

import pytest

from .conftest import LIVE_REPO

pytestmark = pytest.mark.e2e


def test_live_token_and_repo_are_reachable(live_client):
    repo = live_client.get_repo()
    assert repo["full_name"] == LIVE_REPO
