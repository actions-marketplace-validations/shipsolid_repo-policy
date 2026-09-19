import re

import repo_policy


def test_version_is_a_valid_semver_string():
    # Not a hardcoded literal: semantic-release bumps this on every release, and a hardcoded
    # value here is exactly what let __version__ silently diverge from the published version
    # for 4 releases before anyone noticed (confirmed via a real `pip install repo-policy`).
    assert re.match(r"^\d+\.\d+\.\d+$", repo_policy.__version__)
