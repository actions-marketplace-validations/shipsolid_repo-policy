# repo-policy v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the v1 `repo-policy` CLI + GitHub Action: a Python tool that reads a declarative `policy.yml`, diffs it against live GitHub branch protection / repository ruleset state, and can report (`validate`/`audit`/`plan`) or enforce (`apply`) that policy idempotently.

**Architecture:** A Pydantic config layer (`models.py`/`config.py`) parses `policy.yml` into `PolicyConfig`. An `httpx`-based `github_client.py` talks to the GitHub REST API. Two backend translators (`policies/branch_protection.py`, `policies/rulesets.py`, sharing `policies/pull_requests.py` and `policies/status_checks.py`) convert between `BranchPolicy` and each backend's JSON shape. `diff.py` resolves undeclared fields (managed-scope vs strict) and produces a flat `Change` list that `audit.py`, `render.py`, and `apply.py` all consume — one diff function backs every command. `cli.py` (Click) wires it all together with exit codes for CI.

**Tech Stack:** Python 3.10+, httpx, PyYAML, Pydantic v2, Click, pytest, respx, ruff, mypy, hatchling, Docker, python-semantic-release.

**Spec:** [docs/superpowers/specs/2026-09-19-repo-policy-design.md](../specs/2026-09-19-repo-policy-design.md)

## Global Constraints

- Python 3.10+ (from spec §10).
- Runtime deps exactly: `httpx`, `pyyaml`, `pydantic>=2`, `click`. Dev deps exactly: `pytest`, `respx`, `ruff`, `mypy` (spec §10).
- Build backend: `hatchling`. No Poetry, no lockfile (spec §10).
- GitHub API version header `X-GitHub-Api-Version: 2022-11-28` on every request (current API requirement, confirmed against GitHub REST docs during planning).
- `apply` in managed-scope (default) NEVER touches a branch absent from `policy.yml`, and never mutates a ruleset not named `repo-policy:<branch>` (spec §7).
- No state file anywhere — ownership is either "declared in current `policy.yml`" (branch protection) or "matches the `repo-policy:` naming convention" (rulesets) (spec §7).
- Exit codes: 0 = success/compliant/no-op, 1 = drift found, 2 = config/validation error, 3 = GitHub API/auth error (spec §8).
- Auth resolution order: `--token` CLI flag, then `GITHUB_TOKEN`, then `GH_TOKEN` (spec §8).
- Repo resolution order: `--repo owner/name` CLI flag, then `$GITHUB_REPOSITORY`, then the local git `origin` remote (spec §8).

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/repo_policy/__init__.py`
- Create: `src/repo_policy/policies/__init__.py`
- Create: `.gitignore`
- Test: `tests/test_package.py`

**Interfaces:**
- Produces: `repo_policy.__version__: str`, an installed editable package importable as `repo_policy` and `repo_policy.policies`.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "repo-policy"
version = "0.1.0"
description = "Lightweight, declarative repository governance for GitHub."
readme = "README.md"
license = "MIT"
requires-python = ">=3.10"
authors = [{ name = "Amit Singh" }]
dependencies = [
    "httpx>=0.27",
    "pyyaml>=6.0",
    "pydantic>=2.0",
    "click>=8.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "respx>=0.21",
    "ruff>=0.6",
    "mypy>=1.10",
]

[project.scripts]
repo-policy = "repo_policy.cli:main"

[project.urls]
Homepage = "https://github.com/shipsolid/repo-policy"

[tool.hatch.build.targets.wheel]
packages = ["src/repo_policy"]

[tool.ruff]
line-length = 100
src = ["src", "tests"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.mypy]
python_version = "3.10"
ignore_missing_imports = true
```

- [ ] **Step 2: Create the package skeleton**

Create `src/repo_policy/__init__.py`:

```python
__version__ = "0.1.0"
```

Create `src/repo_policy/policies/__init__.py` (empty file — marks the package).

- [ ] **Step 3: Create `.gitignore`**

```gitignore
__pycache__/
*.pyc
.venv/
dist/
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
```

- [ ] **Step 4: Write the failing smoke test**

```python
# tests/test_package.py
import repo_policy


def test_version_is_defined():
    assert repo_policy.__version__ == "0.1.0"
```

- [ ] **Step 5: Run test to verify it fails**

Run: `python -m pytest tests/test_package.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'repo_policy'` (package not installed yet).

- [ ] **Step 6: Install the package in editable mode with dev extras**

Run: `pip install -e ".[dev]"`

- [ ] **Step 7: Run test to verify it passes**

Run: `python -m pytest tests/test_package.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml src/repo_policy/__init__.py src/repo_policy/policies/__init__.py .gitignore tests/test_package.py
git commit -m "chore: scaffold repo-policy package"
```

---

### Task 2: Config models

**Files:**
- Create: `src/repo_policy/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `PullRequestPolicy{required: bool, approvals: int, code_owner_review: bool}`, `StatusChecksPolicy{required: list[str]}`, `BranchPolicy{enforcement: Literal["branch_protection","ruleset"], strict: bool | None, pull_requests: PullRequestPolicy | None, status_checks: StatusChecksPolicy | None, signed_commits: bool | None, linear_history: bool | None, allow_force_push: bool | None, allow_deletion: bool | None}`, `PolicyConfig{version: int, strict: bool, branches: dict[str, BranchPolicy]}`, `effective_strict(config: PolicyConfig, branch: str) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_models.py
import pytest
from pydantic import ValidationError

from repo_policy.models import (
    BranchPolicy,
    PolicyConfig,
    PullRequestPolicy,
    StatusChecksPolicy,
    effective_strict,
)


def test_branch_policy_defaults():
    policy = BranchPolicy()
    assert policy.enforcement == "branch_protection"
    assert policy.strict is None
    assert policy.pull_requests is None


def test_branch_policy_rejects_unknown_enforcement():
    with pytest.raises(ValidationError):
        BranchPolicy(enforcement="bogus")


def test_policy_config_parses_nested_branches():
    config = PolicyConfig(
        version=1,
        branches={
            "main": BranchPolicy(
                pull_requests=PullRequestPolicy(required=True, approvals=2, code_owner_review=True),
                status_checks=StatusChecksPolicy(required=["build", "test"]),
                linear_history=True,
            )
        },
    )
    assert config.branches["main"].pull_requests.approvals == 2
    assert config.branches["main"].status_checks.required == ["build", "test"]


def test_policy_config_rejects_unsupported_version():
    with pytest.raises(ValidationError):
        PolicyConfig(version=2, branches={})


def test_effective_strict_falls_back_to_top_level_default():
    config = PolicyConfig(version=1, strict=True, branches={"main": BranchPolicy()})
    assert effective_strict(config, "main") is True


def test_effective_strict_branch_override_wins():
    config = PolicyConfig(version=1, strict=True, branches={"main": BranchPolicy(strict=False)})
    assert effective_strict(config, "main") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'repo_policy.models'`

- [ ] **Step 3: Implement `models.py`**

```python
# src/repo_policy/models.py
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class PullRequestPolicy(BaseModel):
    required: bool = True
    approvals: int = 1
    code_owner_review: bool = False


class StatusChecksPolicy(BaseModel):
    required: list[str] = Field(default_factory=list)


class BranchPolicy(BaseModel):
    enforcement: Literal["branch_protection", "ruleset"] = "branch_protection"
    strict: Optional[bool] = None
    pull_requests: Optional[PullRequestPolicy] = None
    status_checks: Optional[StatusChecksPolicy] = None
    signed_commits: Optional[bool] = None
    linear_history: Optional[bool] = None
    allow_force_push: Optional[bool] = None
    allow_deletion: Optional[bool] = None


class PolicyConfig(BaseModel):
    version: int
    strict: bool = False
    branches: dict[str, BranchPolicy]

    @field_validator("version")
    @classmethod
    def _version_must_be_supported(cls, value: int) -> int:
        if value != 1:
            raise ValueError(f"unsupported policy version: {value} (only version 1 is supported)")
        return value


def effective_strict(config: PolicyConfig, branch: str) -> bool:
    """A branch's own `strict` always wins; otherwise inherit the top-level default."""
    branch_policy = config.branches[branch]
    return branch_policy.strict if branch_policy.strict is not None else config.strict
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/repo_policy/models.py tests/test_models.py
git commit -m "feat: add PolicyConfig models"
```

---

### Task 3: Config loader (`validate`'s engine)

**Files:**
- Create: `src/repo_policy/config.py`
- Create: `tests/fixtures/policy_valid.yml`
- Create: `tests/fixtures/policy_invalid.yml`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `PolicyConfig` from Task 2 (`repo_policy.models`).
- Produces: `ConfigError(Exception)`, `load_policy(path: str | Path) -> PolicyConfig`.

- [ ] **Step 1: Create fixture files**

```yaml
# tests/fixtures/policy_valid.yml
version: 1

branches:
  main:
    pull_requests:
      required: true
      approvals: 2
      code_owner_review: true
    status_checks:
      required:
        - build
        - test
    signed_commits: true
    linear_history: true
    allow_force_push: false
    allow_deletion: false
```

```yaml
# tests/fixtures/policy_invalid.yml
version: 1

branches:
  main:
    enforcement: not-a-real-backend
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_config.py
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'repo_policy.config'`

- [ ] **Step 4: Implement `config.py`**

```python
# src/repo_policy/config.py
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from repo_policy.models import PolicyConfig


class ConfigError(Exception):
    """Raised when policy.yml is missing, malformed, or fails schema validation."""


def load_policy(path: str | Path) -> PolicyConfig:
    file_path = Path(path)

    if not file_path.exists():
        raise ConfigError(f"policy file not found: {file_path}")

    try:
        raw_text = file_path.read_text()
    except OSError as exc:
        raise ConfigError(f"could not read policy file {file_path}: {exc}") from exc

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {file_path}: {exc}") from exc

    if data is None:
        raise ConfigError(f"policy file is empty: {file_path}")

    try:
        return PolicyConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(file_path, exc)) from exc


def _format_validation_error(path: Path, exc: ValidationError) -> str:
    lines = [f"invalid policy config in {path}:"]
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        lines.append(f"  - {location}: {error['msg']}")
    return "\n".join(lines)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add src/repo_policy/config.py tests/fixtures/policy_valid.yml tests/fixtures/policy_invalid.yml tests/test_config.py
git commit -m "feat: add policy.yml loader with validation errors"
```

---

### Task 4: GitHub client — auth and retrying request core

**Files:**
- Create: `src/repo_policy/github_client.py`
- Test: `tests/test_github_client.py`

**Interfaces:**
- Produces: `GitHubAPIError(Exception, status_code: int | None)`, `GitHubClient(token, owner, repo, base_url="https://api.github.com", client=None, max_retries=3, backoff_seconds=1.0)` with `_request(method, path, *, json=None, allow_404=False) -> httpx.Response | None`, `.close()`, context-manager support.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_github_client.py
import httpx
import pytest
import respx

from repo_policy.github_client import GitHubAPIError, GitHubClient


@pytest.fixture
def client():
    c = GitHubClient(token="test-token", owner="acme", repo="widgets", backoff_seconds=0.0)
    yield c
    c.close()


@respx.mock
def test_request_sends_auth_and_version_headers(client):
    route = respx.get("https://api.github.com/repos/acme/widgets/ping").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    client._request("GET", "/repos/acme/widgets/ping")
    sent = route.calls[0].request
    assert sent.headers["Authorization"] == "Bearer test-token"
    assert sent.headers["X-GitHub-Api-Version"] == "2022-11-28"


@respx.mock
def test_request_returns_none_on_404_when_allowed(client):
    respx.get("https://api.github.com/repos/acme/widgets/missing").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )
    assert client._request("GET", "/repos/acme/widgets/missing", allow_404=True) is None


@respx.mock
def test_request_retries_on_500_then_succeeds(client):
    route = respx.get("https://api.github.com/repos/acme/widgets/flaky")
    route.side_effect = [
        httpx.Response(500, json={"message": "boom"}),
        httpx.Response(200, json={"ok": True}),
    ]
    response = client._request("GET", "/repos/acme/widgets/flaky")
    assert response.json() == {"ok": True}
    assert route.call_count == 2


@respx.mock
def test_request_raises_after_exhausting_retries(client):
    respx.get("https://api.github.com/repos/acme/widgets/broken").mock(
        return_value=httpx.Response(500, json={"message": "boom"})
    )
    with pytest.raises(GitHubAPIError) as exc_info:
        client._request("GET", "/repos/acme/widgets/broken")
    assert exc_info.value.status_code == 500


@respx.mock
def test_request_raises_immediately_on_non_retryable_4xx(client):
    route = respx.get("https://api.github.com/repos/acme/widgets/forbidden").mock(
        return_value=httpx.Response(401, json={"message": "Bad credentials"})
    )
    with pytest.raises(GitHubAPIError) as exc_info:
        client._request("GET", "/repos/acme/widgets/forbidden")
    assert exc_info.value.status_code == 401
    assert route.call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_github_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'repo_policy.github_client'`

- [ ] **Step 3: Implement the client core**

```python
# src/repo_policy/github_client.py
from __future__ import annotations

import time

import httpx


class GitHubAPIError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class GitHubClient:
    def __init__(
        self,
        token: str,
        owner: str,
        repo: str,
        base_url: str = "https://api.github.com",
        client: httpx.Client | None = None,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
    ) -> None:
        self.owner = owner
        self.repo = repo
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds
        self._client = client or httpx.Client(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        allow_404: bool = False,
    ) -> httpx.Response | None:
        attempt = 0
        while True:
            response = self._client.request(method, path, json=json)

            if response.status_code == 404 and allow_404:
                return None
            if response.status_code < 400:
                return response

            is_rate_limited = response.status_code == 403 and "rate limit" in response.text.lower()
            is_retryable = is_rate_limited or response.status_code >= 500

            if is_retryable and attempt < self._max_retries:
                time.sleep(self._backoff_seconds * (2**attempt))
                attempt += 1
                continue

            raise GitHubAPIError(
                f"GitHub API error {response.status_code} on {method} {path}: {response.text}",
                status_code=response.status_code,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_github_client.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/repo_policy/github_client.py tests/test_github_client.py
git commit -m "feat: add GitHubClient with retrying request core"
```

---

### Task 5: GitHub client — branch protection + signed commits

**Files:**
- Modify: `src/repo_policy/github_client.py`
- Modify: `tests/test_github_client.py`

**Interfaces:**
- Consumes: `GitHubClient._request` from Task 4.
- Produces: `GitHubClient.get_branch_protection(branch: str) -> dict | None`, `.put_branch_protection(branch: str, payload: dict) -> dict`, `.get_required_signatures(branch: str) -> bool`, `.set_required_signatures(branch: str, enabled: bool) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_github_client.py`:

```python
@respx.mock
def test_get_branch_protection_returns_none_when_unprotected(client):
    respx.get("https://api.github.com/repos/acme/widgets/branches/main/protection").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )
    assert client.get_branch_protection("main") is None


@respx.mock
def test_get_branch_protection_returns_payload(client):
    respx.get("https://api.github.com/repos/acme/widgets/branches/main/protection").mock(
        return_value=httpx.Response(200, json={"enforce_admins": {"enabled": False}})
    )
    assert client.get_branch_protection("main") == {"enforce_admins": {"enabled": False}}


@respx.mock
def test_put_branch_protection_sends_payload(client):
    route = respx.put("https://api.github.com/repos/acme/widgets/branches/main/protection").mock(
        return_value=httpx.Response(200, json={"enforce_admins": {"enabled": False}})
    )
    result = client.put_branch_protection("main", {"enforce_admins": False})
    assert result == {"enforce_admins": {"enabled": False}}
    assert route.calls[0].request.content == b'{"enforce_admins": false}'


@respx.mock
def test_get_required_signatures_false_when_never_enabled(client):
    respx.get(
        "https://api.github.com/repos/acme/widgets/branches/main/protection/required_signatures"
    ).mock(return_value=httpx.Response(404, json={"message": "Not Found"}))
    assert client.get_required_signatures("main") is False


@respx.mock
def test_get_required_signatures_true_when_enabled(client):
    respx.get(
        "https://api.github.com/repos/acme/widgets/branches/main/protection/required_signatures"
    ).mock(return_value=httpx.Response(200, json={"enabled": True}))
    assert client.get_required_signatures("main") is True


@respx.mock
def test_set_required_signatures_posts_to_enable(client):
    route = respx.post(
        "https://api.github.com/repos/acme/widgets/branches/main/protection/required_signatures"
    ).mock(return_value=httpx.Response(200, json={"enabled": True}))
    client.set_required_signatures("main", True)
    assert route.called


@respx.mock
def test_set_required_signatures_deletes_to_disable(client):
    route = respx.delete(
        "https://api.github.com/repos/acme/widgets/branches/main/protection/required_signatures"
    ).mock(return_value=httpx.Response(204))
    client.set_required_signatures("main", False)
    assert route.called
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_github_client.py -v`
Expected: FAIL with `AttributeError: 'GitHubClient' object has no attribute 'get_branch_protection'`

- [ ] **Step 3: Add the branch protection methods**

Append to `src/repo_policy/github_client.py` (inside `GitHubClient`):

```python
    def get_branch_protection(self, branch: str) -> dict | None:
        response = self._request(
            "GET", f"/repos/{self.owner}/{self.repo}/branches/{branch}/protection", allow_404=True
        )
        return response.json() if response is not None else None

    def put_branch_protection(self, branch: str, payload: dict) -> dict:
        response = self._request(
            "PUT", f"/repos/{self.owner}/{self.repo}/branches/{branch}/protection", json=payload
        )
        assert response is not None
        return response.json()

    def get_required_signatures(self, branch: str) -> bool:
        response = self._request(
            "GET",
            f"/repos/{self.owner}/{self.repo}/branches/{branch}/protection/required_signatures",
            allow_404=True,
        )
        return bool(response is not None and response.json().get("enabled", False))

    def set_required_signatures(self, branch: str, enabled: bool) -> None:
        method = "POST" if enabled else "DELETE"
        self._request(
            method,
            f"/repos/{self.owner}/{self.repo}/branches/{branch}/protection/required_signatures",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_github_client.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add src/repo_policy/github_client.py tests/test_github_client.py
git commit -m "feat: add branch protection and required-signatures client methods"
```

---

### Task 6: GitHub client — rulesets

**Files:**
- Modify: `src/repo_policy/github_client.py`
- Modify: `tests/test_github_client.py`

**Interfaces:**
- Consumes: `GitHubClient._request` from Task 4.
- Produces: `GitHubClient.list_rulesets() -> list[dict]`, `.get_ruleset(ruleset_id: int) -> dict`, `.find_ruleset_by_name(name: str) -> dict | None`, `.create_ruleset(payload: dict) -> dict`, `.update_ruleset(ruleset_id: int, payload: dict) -> dict`, `.delete_ruleset(ruleset_id: int) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_github_client.py`:

```python
@respx.mock
def test_list_rulesets_returns_summaries(client):
    respx.get("https://api.github.com/repos/acme/widgets/rulesets").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "name": "repo-policy:main"}])
    )
    assert client.list_rulesets() == [{"id": 1, "name": "repo-policy:main"}]


@respx.mock
def test_get_ruleset_returns_full_detail(client):
    respx.get("https://api.github.com/repos/acme/widgets/rulesets/1").mock(
        return_value=httpx.Response(200, json={"id": 1, "name": "repo-policy:main", "rules": []})
    )
    assert client.get_ruleset(1) == {"id": 1, "name": "repo-policy:main", "rules": []}


@respx.mock
def test_find_ruleset_by_name_returns_full_detail_when_present(client):
    respx.get("https://api.github.com/repos/acme/widgets/rulesets").mock(
        return_value=httpx.Response(
            200, json=[{"id": 1, "name": "repo-policy:main"}, {"id": 2, "name": "other"}]
        )
    )
    respx.get("https://api.github.com/repos/acme/widgets/rulesets/1").mock(
        return_value=httpx.Response(200, json={"id": 1, "name": "repo-policy:main", "rules": []})
    )
    result = client.find_ruleset_by_name("repo-policy:main")
    assert result == {"id": 1, "name": "repo-policy:main", "rules": []}


@respx.mock
def test_find_ruleset_by_name_returns_none_when_absent(client):
    respx.get("https://api.github.com/repos/acme/widgets/rulesets").mock(
        return_value=httpx.Response(200, json=[{"id": 2, "name": "other"}])
    )
    assert client.find_ruleset_by_name("repo-policy:main") is None


@respx.mock
def test_create_ruleset_posts_payload(client):
    route = respx.post("https://api.github.com/repos/acme/widgets/rulesets").mock(
        return_value=httpx.Response(201, json={"id": 5, "name": "repo-policy:main"})
    )
    result = client.create_ruleset({"name": "repo-policy:main"})
    assert result["id"] == 5
    assert route.called


@respx.mock
def test_update_ruleset_puts_payload(client):
    route = respx.put("https://api.github.com/repos/acme/widgets/rulesets/5").mock(
        return_value=httpx.Response(200, json={"id": 5, "name": "repo-policy:main"})
    )
    client.update_ruleset(5, {"name": "repo-policy:main"})
    assert route.called


@respx.mock
def test_delete_ruleset_calls_delete(client):
    route = respx.delete("https://api.github.com/repos/acme/widgets/rulesets/5").mock(
        return_value=httpx.Response(204)
    )
    client.delete_ruleset(5)
    assert route.called
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_github_client.py -v`
Expected: FAIL with `AttributeError: 'GitHubClient' object has no attribute 'list_rulesets'`

- [ ] **Step 3: Add the ruleset methods**

Append to `src/repo_policy/github_client.py` (inside `GitHubClient`):

```python
    def list_rulesets(self) -> list[dict]:
        response = self._request("GET", f"/repos/{self.owner}/{self.repo}/rulesets")
        assert response is not None
        return response.json()

    def get_ruleset(self, ruleset_id: int) -> dict:
        response = self._request("GET", f"/repos/{self.owner}/{self.repo}/rulesets/{ruleset_id}")
        assert response is not None
        return response.json()

    def find_ruleset_by_name(self, name: str) -> dict | None:
        for summary in self.list_rulesets():
            if summary["name"] == name:
                return self.get_ruleset(summary["id"])
        return None

    def create_ruleset(self, payload: dict) -> dict:
        response = self._request("POST", f"/repos/{self.owner}/{self.repo}/rulesets", json=payload)
        assert response is not None
        return response.json()

    def update_ruleset(self, ruleset_id: int, payload: dict) -> dict:
        response = self._request(
            "PUT", f"/repos/{self.owner}/{self.repo}/rulesets/{ruleset_id}", json=payload
        )
        assert response is not None
        return response.json()

    def delete_ruleset(self, ruleset_id: int) -> None:
        self._request("DELETE", f"/repos/{self.owner}/{self.repo}/rulesets/{ruleset_id}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_github_client.py -v`
Expected: PASS (19 tests)

- [ ] **Step 5: Commit**

```bash
git add src/repo_policy/github_client.py tests/test_github_client.py
git commit -m "feat: add ruleset CRUD to GitHubClient"
```

---

### Task 7: Shared policy translators — pull requests + status checks

**Files:**
- Create: `src/repo_policy/policies/pull_requests.py`
- Create: `src/repo_policy/policies/status_checks.py`
- Test: `tests/test_policies_pull_requests.py`
- Test: `tests/test_policies_status_checks.py`

**Interfaces:**
- Consumes: `PullRequestPolicy`, `StatusChecksPolicy` from Task 2.
- Produces: `pull_requests.to_branch_protection(policy) -> dict | None`, `pull_requests.from_branch_protection(data: dict | None) -> PullRequestPolicy`, `pull_requests.to_ruleset_rule(policy) -> dict | None`, `pull_requests.from_ruleset_rule(rule: dict | None) -> PullRequestPolicy`; the same four function names/shapes in `status_checks.py` for `StatusChecksPolicy`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_policies_pull_requests.py
from repo_policy.models import PullRequestPolicy
from repo_policy.policies import pull_requests


def test_to_branch_protection_none_when_not_required():
    assert pull_requests.to_branch_protection(PullRequestPolicy(required=False)) is None


def test_to_branch_protection_builds_payload():
    policy = PullRequestPolicy(required=True, approvals=2, code_owner_review=True)
    payload = pull_requests.to_branch_protection(policy)
    assert payload["required_approving_review_count"] == 2
    assert payload["require_code_owner_reviews"] is True


def test_from_branch_protection_none_means_not_required():
    result = pull_requests.from_branch_protection(None)
    assert result.required is False
    assert result.approvals == 0


def test_from_branch_protection_reads_payload():
    data = {"required_approving_review_count": 3, "require_code_owner_reviews": True}
    result = pull_requests.from_branch_protection(data)
    assert result == PullRequestPolicy(required=True, approvals=3, code_owner_review=True)


def test_to_ruleset_rule_none_when_not_required():
    assert pull_requests.to_ruleset_rule(PullRequestPolicy(required=False)) is None


def test_to_ruleset_rule_builds_rule():
    policy = PullRequestPolicy(required=True, approvals=1, code_owner_review=False)
    rule = pull_requests.to_ruleset_rule(policy)
    assert rule["type"] == "pull_request"
    assert rule["parameters"]["required_approving_review_count"] == 1


def test_from_ruleset_rule_none_means_not_required():
    result = pull_requests.from_ruleset_rule(None)
    assert result.required is False


def test_from_ruleset_rule_reads_rule():
    rule = {
        "type": "pull_request",
        "parameters": {"required_approving_review_count": 2, "require_code_owner_review": True},
    }
    result = pull_requests.from_ruleset_rule(rule)
    assert result == PullRequestPolicy(required=True, approvals=2, code_owner_review=True)
```

```python
# tests/test_policies_status_checks.py
from repo_policy.models import StatusChecksPolicy
from repo_policy.policies import status_checks


def test_to_branch_protection_none_when_empty():
    assert status_checks.to_branch_protection(None) is None
    assert status_checks.to_branch_protection(StatusChecksPolicy(required=[])) is None


def test_to_branch_protection_builds_payload():
    payload = status_checks.to_branch_protection(StatusChecksPolicy(required=["build", "test"]))
    assert payload["contexts"] == ["build", "test"]
    assert payload["checks"] == [
        {"context": "build", "app_id": None},
        {"context": "test", "app_id": None},
    ]


def test_from_branch_protection_none_when_absent():
    assert status_checks.from_branch_protection(None) is None


def test_from_branch_protection_reads_contexts():
    result = status_checks.from_branch_protection({"contexts": ["build"], "checks": []})
    assert result == StatusChecksPolicy(required=["build"])


def test_to_ruleset_rule_none_when_empty():
    assert status_checks.to_ruleset_rule(StatusChecksPolicy(required=[])) is None


def test_to_ruleset_rule_builds_rule():
    rule = status_checks.to_ruleset_rule(StatusChecksPolicy(required=["build"]))
    assert rule["type"] == "required_status_checks"
    assert rule["parameters"]["required_status_checks"] == [{"context": "build"}]


def test_from_ruleset_rule_none_when_absent():
    assert status_checks.from_ruleset_rule(None) is None


def test_from_ruleset_rule_reads_rule():
    rule = {"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "build"}]}}
    result = status_checks.from_ruleset_rule(rule)
    assert result == StatusChecksPolicy(required=["build"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_policies_pull_requests.py tests/test_policies_status_checks.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'repo_policy.policies.pull_requests'`

- [ ] **Step 3: Implement `pull_requests.py`**

```python
# src/repo_policy/policies/pull_requests.py
from __future__ import annotations

from repo_policy.models import PullRequestPolicy


def to_branch_protection(policy: PullRequestPolicy) -> dict | None:
    if not policy.required:
        return None
    return {
        "required_approving_review_count": policy.approvals,
        "require_code_owner_reviews": policy.code_owner_review,
        "dismiss_stale_reviews": False,
        "require_last_push_approval": False,
    }


def from_branch_protection(data: dict | None) -> PullRequestPolicy:
    if data is None:
        return PullRequestPolicy(required=False, approvals=0, code_owner_review=False)
    return PullRequestPolicy(
        required=True,
        approvals=data.get("required_approving_review_count", 0),
        code_owner_review=data.get("require_code_owner_reviews", False),
    )


def to_ruleset_rule(policy: PullRequestPolicy) -> dict | None:
    if not policy.required:
        return None
    return {
        "type": "pull_request",
        "parameters": {
            "required_approving_review_count": policy.approvals,
            "require_code_owner_review": policy.code_owner_review,
            "require_last_push_approval": False,
            "dismiss_stale_reviews_on_push": False,
            "required_review_thread_resolution": False,
        },
    }


def from_ruleset_rule(rule: dict | None) -> PullRequestPolicy:
    if rule is None:
        return PullRequestPolicy(required=False, approvals=0, code_owner_review=False)
    params = rule["parameters"]
    return PullRequestPolicy(
        required=True,
        approvals=params.get("required_approving_review_count", 0),
        code_owner_review=params.get("require_code_owner_review", False),
    )
```

- [ ] **Step 4: Implement `status_checks.py`**

```python
# src/repo_policy/policies/status_checks.py
from __future__ import annotations

from repo_policy.models import StatusChecksPolicy


def to_branch_protection(policy: StatusChecksPolicy | None) -> dict | None:
    if policy is None or not policy.required:
        return None
    return {
        "strict": False,
        "contexts": list(policy.required),
        "checks": [{"context": name, "app_id": None} for name in policy.required],
    }


def from_branch_protection(data: dict | None) -> StatusChecksPolicy | None:
    if data is None:
        return None
    contexts = data.get("contexts") or [check["context"] for check in data.get("checks", [])]
    if not contexts:
        return None
    return StatusChecksPolicy(required=list(contexts))


def to_ruleset_rule(policy: StatusChecksPolicy | None) -> dict | None:
    if policy is None or not policy.required:
        return None
    return {
        "type": "required_status_checks",
        "parameters": {
            "required_status_checks": [{"context": name} for name in policy.required],
            "strict_required_status_checks_policy": False,
        },
    }


def from_ruleset_rule(rule: dict | None) -> StatusChecksPolicy | None:
    if rule is None:
        return None
    checks = rule["parameters"].get("required_status_checks", [])
    if not checks:
        return None
    return StatusChecksPolicy(required=[check["context"] for check in checks])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_policies_pull_requests.py tests/test_policies_status_checks.py -v`
Expected: PASS (16 tests)

- [ ] **Step 6: Commit**

```bash
git add src/repo_policy/policies/pull_requests.py src/repo_policy/policies/status_checks.py tests/test_policies_pull_requests.py tests/test_policies_status_checks.py
git commit -m "feat: add shared pull_requests and status_checks translators"
```

---

### Task 8: Branch protection translator

**Files:**
- Create: `src/repo_policy/policies/branch_protection.py`
- Test: `tests/test_policies_branch_protection.py`

**Interfaces:**
- Consumes: `BranchPolicy` (Task 2), `pull_requests`/`status_checks` translators (Task 7).
- Produces: `branch_protection.from_api(data: dict | None, *, signed_commits: bool) -> BranchPolicy`, `branch_protection.to_api_payload(resolved: BranchPolicy, current_raw: dict | None) -> dict`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_policies_branch_protection.py
from repo_policy.models import BranchPolicy, PullRequestPolicy, StatusChecksPolicy
from repo_policy.policies import branch_protection


def test_from_api_none_means_fully_permissive():
    result = branch_protection.from_api(None, signed_commits=False)
    assert result.pull_requests == PullRequestPolicy(required=False, approvals=0, code_owner_review=False)
    assert result.status_checks is None
    assert result.signed_commits is False
    assert result.linear_history is False
    assert result.allow_force_push is True
    assert result.allow_deletion is True


def test_from_api_reads_wrapped_booleans():
    data = {
        "required_pull_request_reviews": {"required_approving_review_count": 2, "require_code_owner_reviews": True},
        "required_status_checks": {"contexts": ["build"], "checks": []},
        "required_linear_history": {"enabled": True},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
    }
    result = branch_protection.from_api(data, signed_commits=True)
    assert result.pull_requests == PullRequestPolicy(required=True, approvals=2, code_owner_review=True)
    assert result.status_checks == StatusChecksPolicy(required=["build"])
    assert result.linear_history is True
    assert result.allow_force_push is False
    assert result.allow_deletion is False
    assert result.signed_commits is True


def test_to_api_payload_builds_full_replace_body():
    resolved = BranchPolicy(
        pull_requests=PullRequestPolicy(required=True, approvals=2, code_owner_review=True),
        status_checks=StatusChecksPolicy(required=["build"]),
        linear_history=True,
        allow_force_push=False,
        allow_deletion=False,
    )
    payload = branch_protection.to_api_payload(resolved, current_raw=None)
    assert payload["enforce_admins"] is False
    assert payload["restrictions"] is None
    assert payload["required_pull_request_reviews"]["required_approving_review_count"] == 2
    assert payload["required_status_checks"]["contexts"] == ["build"]
    assert payload["required_linear_history"] is True
    assert payload["allow_force_pushes"] is False
    assert payload["allow_deletions"] is False


def test_to_api_payload_preserves_unmodeled_current_fields():
    current_raw = {
        "enforce_admins": {"enabled": True},
        "restrictions": {"users": ["octocat"], "teams": []},
    }
    resolved = BranchPolicy(
        pull_requests=PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
        linear_history=False,
        allow_force_push=True,
        allow_deletion=True,
    )
    payload = branch_protection.to_api_payload(resolved, current_raw=current_raw)
    assert payload["enforce_admins"] is True
    assert payload["restrictions"] == {"users": ["octocat"], "teams": []}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_policies_branch_protection.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'repo_policy.policies.branch_protection'`

- [ ] **Step 3: Implement `branch_protection.py`**

```python
# src/repo_policy/policies/branch_protection.py
from __future__ import annotations

from repo_policy.models import BranchPolicy, PullRequestPolicy, StatusChecksPolicy
from repo_policy.policies import pull_requests, status_checks


def _unwrap(value: object, default: bool) -> bool:
    """GitHub's GET response wraps some booleans as {"enabled": bool}; PUT wants raw bool."""
    if isinstance(value, dict):
        return bool(value.get("enabled", default))
    if value is None:
        return default
    return bool(value)


def from_api(data: dict | None, *, signed_commits: bool) -> BranchPolicy:
    if data is None:
        return BranchPolicy(
            enforcement="branch_protection",
            pull_requests=PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
            status_checks=None,
            signed_commits=signed_commits,
            linear_history=False,
            allow_force_push=True,
            allow_deletion=True,
        )
    return BranchPolicy(
        enforcement="branch_protection",
        pull_requests=pull_requests.from_branch_protection(data.get("required_pull_request_reviews")),
        status_checks=status_checks.from_branch_protection(data.get("required_status_checks")),
        signed_commits=signed_commits,
        linear_history=_unwrap(data.get("required_linear_history"), False),
        allow_force_push=_unwrap(data.get("allow_force_pushes"), True),
        allow_deletion=_unwrap(data.get("allow_deletions"), True),
    )


def to_api_payload(resolved: BranchPolicy, current_raw: dict | None) -> dict:
    """`resolved` must already have every modeled field filled in (see diff.resolve_desired) —
    this only reads `current_raw` for the two fields the v1 schema doesn't model but the PUT
    endpoint requires (`enforce_admins`, `restrictions`), preserving whatever is already there."""
    current_raw = current_raw or {}
    assert resolved.pull_requests is not None
    return {
        "enforce_admins": _unwrap(current_raw.get("enforce_admins"), False),
        "restrictions": current_raw.get("restrictions"),
        "required_pull_request_reviews": pull_requests.to_branch_protection(resolved.pull_requests),
        "required_status_checks": status_checks.to_branch_protection(resolved.status_checks),
        "required_linear_history": bool(resolved.linear_history),
        "allow_force_pushes": bool(resolved.allow_force_push),
        "allow_deletions": bool(resolved.allow_deletion),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_policies_branch_protection.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/repo_policy/policies/branch_protection.py tests/test_policies_branch_protection.py
git commit -m "feat: add branch_protection API translator"
```

---

### Task 9: Ruleset translator

**Files:**
- Create: `src/repo_policy/policies/rulesets.py`
- Test: `tests/test_policies_rulesets.py`

**Interfaces:**
- Consumes: `BranchPolicy` (Task 2), `pull_requests`/`status_checks` translators (Task 7).
- Produces: `rulesets.ruleset_name(branch: str) -> str`, `rulesets.from_api(data: dict | None) -> BranchPolicy`, `rulesets.to_api_payload(branch: str, resolved: BranchPolicy) -> dict`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_policies_rulesets.py
from repo_policy.models import BranchPolicy, PullRequestPolicy, StatusChecksPolicy
from repo_policy.policies import rulesets


def test_ruleset_name_is_deterministic():
    assert rulesets.ruleset_name("main") == "repo-policy:main"


def test_from_api_none_means_fully_permissive():
    result = rulesets.from_api(None)
    assert result.pull_requests == PullRequestPolicy(required=False, approvals=0, code_owner_review=False)
    assert result.status_checks is None
    assert result.signed_commits is False
    assert result.linear_history is False
    assert result.allow_force_push is True
    assert result.allow_deletion is True


def test_from_api_reads_rules_array():
    data = {
        "rules": [
            {"type": "pull_request", "parameters": {"required_approving_review_count": 1, "require_code_owner_review": False}},
            {"type": "required_signatures"},
            {"type": "non_fast_forward"},
        ]
    }
    result = rulesets.from_api(data)
    assert result.pull_requests == PullRequestPolicy(required=True, approvals=1, code_owner_review=False)
    assert result.signed_commits is True
    assert result.linear_history is False
    assert result.allow_force_push is False
    assert result.allow_deletion is True


def test_to_api_payload_builds_ruleset_targeting_branch():
    resolved = BranchPolicy(
        pull_requests=PullRequestPolicy(required=True, approvals=2, code_owner_review=True),
        status_checks=StatusChecksPolicy(required=["build"]),
        signed_commits=True,
        linear_history=True,
        allow_force_push=False,
        allow_deletion=False,
    )
    payload = rulesets.to_api_payload("main", resolved)
    assert payload["name"] == "repo-policy:main"
    assert payload["target"] == "branch"
    assert payload["enforcement"] == "active"
    assert payload["conditions"]["ref_name"]["include"] == ["refs/heads/main"]
    rule_types = {rule["type"] for rule in payload["rules"]}
    assert rule_types == {
        "pull_request",
        "required_status_checks",
        "required_signatures",
        "required_linear_history",
        "non_fast_forward",
        "deletion",
    }


def test_to_api_payload_omits_rules_for_permissive_fields():
    resolved = BranchPolicy(
        pull_requests=PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
        status_checks=None,
        signed_commits=False,
        linear_history=False,
        allow_force_push=True,
        allow_deletion=True,
    )
    payload = rulesets.to_api_payload("main", resolved)
    assert payload["rules"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_policies_rulesets.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'repo_policy.policies.rulesets'`

- [ ] **Step 3: Implement `rulesets.py`**

```python
# src/repo_policy/policies/rulesets.py
from __future__ import annotations

from repo_policy.models import BranchPolicy, PullRequestPolicy
from repo_policy.policies import pull_requests, status_checks


def ruleset_name(branch: str) -> str:
    return f"repo-policy:{branch}"


def from_api(data: dict | None) -> BranchPolicy:
    if data is None:
        return BranchPolicy(
            enforcement="ruleset",
            pull_requests=PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
            status_checks=None,
            signed_commits=False,
            linear_history=False,
            allow_force_push=True,
            allow_deletion=True,
        )
    rules_by_type = {rule["type"]: rule for rule in data.get("rules", [])}
    return BranchPolicy(
        enforcement="ruleset",
        pull_requests=pull_requests.from_ruleset_rule(rules_by_type.get("pull_request")),
        status_checks=status_checks.from_ruleset_rule(rules_by_type.get("required_status_checks")),
        signed_commits="required_signatures" in rules_by_type,
        linear_history="required_linear_history" in rules_by_type,
        allow_force_push="non_fast_forward" not in rules_by_type,
        allow_deletion="deletion" not in rules_by_type,
    )


def to_api_payload(branch: str, resolved: BranchPolicy) -> dict:
    """`resolved` must already have every modeled field filled in (see diff.resolve_desired).
    Rulesets are fully owned by repo-policy once named, so this is a full replace of the rules
    array — there are no unmodeled fields to preserve, unlike branch_protection.to_api_payload."""
    assert resolved.pull_requests is not None
    rules: list[dict] = []

    pr_rule = pull_requests.to_ruleset_rule(resolved.pull_requests)
    if pr_rule is not None:
        rules.append(pr_rule)

    sc_rule = status_checks.to_ruleset_rule(resolved.status_checks)
    if sc_rule is not None:
        rules.append(sc_rule)

    if resolved.signed_commits:
        rules.append({"type": "required_signatures"})
    if resolved.linear_history:
        rules.append({"type": "required_linear_history"})
    if resolved.allow_force_push is False:
        rules.append({"type": "non_fast_forward"})
    if resolved.allow_deletion is False:
        rules.append({"type": "deletion"})

    return {
        "name": ruleset_name(branch),
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": [f"refs/heads/{branch}"], "exclude": []}},
        "rules": rules,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_policies_rulesets.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/repo_policy/policies/rulesets.py tests/test_policies_rulesets.py
git commit -m "feat: add ruleset API translator"
```

---

### Task 10: Diff engine

**Files:**
- Create: `src/repo_policy/diff.py`
- Test: `tests/test_diff.py`

**Interfaces:**
- Consumes: `BranchPolicy`, `PullRequestPolicy`, `StatusChecksPolicy` from Task 2.
- Produces: `Change(field: str, current_value, desired_value, action: Literal["add","modify","remove"])` (frozen dataclass), `diff(desired: BranchPolicy, current: BranchPolicy) -> list[Change]`, `resolve_desired(desired: BranchPolicy, current: BranchPolicy, *, strict: bool) -> BranchPolicy`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_diff.py
from repo_policy.models import BranchPolicy, PullRequestPolicy, StatusChecksPolicy
from repo_policy.diff import diff, resolve_desired

PERMISSIVE = BranchPolicy(
    pull_requests=PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
    status_checks=None,
    signed_commits=False,
    linear_history=False,
    allow_force_push=True,
    allow_deletion=True,
)


def test_diff_empty_when_equal():
    assert diff(PERMISSIVE, PERMISSIVE) == []


def test_diff_detects_modify():
    desired = PERMISSIVE.model_copy(update={"linear_history": True})
    changes = diff(desired, PERMISSIVE)
    assert len(changes) == 1
    assert changes[0].field == "linear_history"
    assert changes[0].action == "add"


def test_diff_detects_approvals_increase_as_modify():
    current = PERMISSIVE.model_copy(
        update={"pull_requests": PullRequestPolicy(required=True, approvals=1, code_owner_review=False)}
    )
    desired = PERMISSIVE.model_copy(
        update={"pull_requests": PullRequestPolicy(required=True, approvals=2, code_owner_review=False)}
    )
    changes = diff(desired, current)
    assert len(changes) == 1
    assert changes[0].field == "pull_requests"
    assert changes[0].action == "modify"


def test_diff_detects_remove():
    current = PERMISSIVE.model_copy(update={"allow_force_push": False})
    desired = PERMISSIVE.model_copy(update={"allow_force_push": True})
    changes = diff(desired, current)
    assert len(changes) == 1
    assert changes[0].action == "remove"


def test_resolve_desired_managed_scope_inherits_current_for_unset_fields():
    desired = BranchPolicy(linear_history=True)  # everything else left unset
    current = PERMISSIVE.model_copy(
        update={"pull_requests": PullRequestPolicy(required=True, approvals=3, code_owner_review=True)}
    )
    resolved = resolve_desired(desired, current, strict=False)
    assert resolved.linear_history is True
    assert resolved.pull_requests == PullRequestPolicy(required=True, approvals=3, code_owner_review=True)
    assert diff(resolved, current) == [
        change for change in diff(resolved, current) if change.field == "linear_history"
    ]


def test_resolve_desired_strict_uses_schema_defaults_for_unset_fields():
    desired = BranchPolicy(linear_history=True)
    current = BranchPolicy(
        pull_requests=PullRequestPolicy(required=True, approvals=3, code_owner_review=True),
        status_checks=StatusChecksPolicy(required=["build"]),
        signed_commits=True,
        linear_history=False,
        allow_force_push=False,
        allow_deletion=False,
    )
    resolved = resolve_desired(desired, current, strict=True)
    assert resolved.pull_requests == PullRequestPolicy(required=False, approvals=0, code_owner_review=False)
    assert resolved.status_checks == StatusChecksPolicy(required=[])
    assert resolved.signed_commits is False
    assert resolved.allow_force_push is True
    assert resolved.allow_deletion is True
    # strict still respects fields the branch DID declare
    assert resolved.linear_history is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_diff.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'repo_policy.diff'`

- [ ] **Step 3: Implement `diff.py`**

```python
# src/repo_policy/diff.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from repo_policy.models import BranchPolicy, PullRequestPolicy, StatusChecksPolicy

ChangeAction = Literal["add", "modify", "remove"]

_FIELDS = (
    "pull_requests",
    "status_checks",
    "signed_commits",
    "linear_history",
    "allow_force_push",
    "allow_deletion",
)

_SCHEMA_DEFAULTS: dict[str, Any] = {
    "pull_requests": PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
    "status_checks": StatusChecksPolicy(required=[]),
    "signed_commits": False,
    "linear_history": False,
    "allow_force_push": True,
    "allow_deletion": True,
}


@dataclass(frozen=True)
class Change:
    field: str
    current_value: Any
    desired_value: Any
    action: ChangeAction


def resolve_desired(desired: BranchPolicy, current: BranchPolicy, *, strict: bool) -> BranchPolicy:
    """Fill in every undeclared (None) field: from `current` in managed-scope mode, or from the
    permissive schema default in strict mode. The result always has every field concretely set,
    so `diff()` never has to special-case None."""
    resolved: dict[str, Any] = {}
    for field in _FIELDS:
        value = getattr(desired, field)
        if value is not None:
            resolved[field] = value
        elif strict:
            resolved[field] = _SCHEMA_DEFAULTS[field]
        else:
            resolved[field] = getattr(current, field)
    return desired.model_copy(update=resolved)


def diff(desired: BranchPolicy, current: BranchPolicy) -> list[Change]:
    changes: list[Change] = []
    for field in _FIELDS:
        desired_value = getattr(desired, field)
        current_value = getattr(current, field)
        if desired_value == current_value:
            continue
        changes.append(
            Change(
                field=field,
                current_value=current_value,
                desired_value=desired_value,
                action=_classify_action(current_value, desired_value),
            )
        )
    return changes


def _classify_action(current_value: Any, desired_value: Any) -> ChangeAction:
    if _is_empty(current_value):
        return "add"
    if _is_empty(desired_value):
        return "remove"
    return "modify"


def _is_empty(value: Any) -> bool:
    if value is None or value is False:
        return True
    if isinstance(value, (list, dict)) and not value:
        return True
    if hasattr(value, "required"):
        required = value.required
        return required is False if isinstance(required, bool) else len(required) == 0
    return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_diff.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/repo_policy/diff.py tests/test_diff.py
git commit -m "feat: add diff engine with managed-scope and strict resolution"
```

---

### Task 11: Apply engine

**Files:**
- Create: `src/repo_policy/apply.py`
- Test: `tests/test_apply.py`

**Interfaces:**
- Consumes: `GitHubClient` (Task 4-6), `PolicyConfig`, `BranchPolicy`, `effective_strict` (Task 2), `diff`/`resolve_desired`/`Change` (Task 10), `branch_protection`/`rulesets` translators (Task 8-9).
- Produces: `BranchResult(branch: str, changes: list[Change], applied: bool)`, `fetch_current(client, branch, enforcement) -> tuple[BranchPolicy, dict | None, int | None]`, `plan_branch(client, config, branch) -> tuple[list[Change], BranchPolicy]`, `apply_branch(client, config, branch) -> BranchResult`, `apply_all(client, config) -> list[BranchResult]`, `prune_rulesets(client, config) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_apply.py
from unittest.mock import MagicMock

from repo_policy.apply import apply_all, apply_branch, plan_branch, prune_rulesets
from repo_policy.models import BranchPolicy, PolicyConfig, PullRequestPolicy


def _config(**branch_kwargs) -> PolicyConfig:
    return PolicyConfig(version=1, branches={"main": BranchPolicy(**branch_kwargs)})


def test_plan_branch_reports_no_changes_when_already_compliant():
    client = MagicMock()
    client.get_branch_protection.return_value = None
    client.get_required_signatures.return_value = False
    config = _config()  # every field left unset -> managed-scope compares against itself
    changes, resolved = plan_branch(client, config, "main")
    assert changes == []


def test_apply_branch_skips_api_calls_when_no_changes():
    client = MagicMock()
    client.get_branch_protection.return_value = None
    client.get_required_signatures.return_value = False
    config = _config()
    result = apply_branch(client, config, "main")
    assert result.applied is False
    client.put_branch_protection.assert_not_called()


def test_apply_branch_puts_protection_when_changes_exist():
    client = MagicMock()
    client.get_branch_protection.return_value = None
    client.get_required_signatures.return_value = False
    config = _config(
        pull_requests=PullRequestPolicy(required=True, approvals=2, code_owner_review=True),
        linear_history=True,
    )
    result = apply_branch(client, config, "main")
    assert result.applied is True
    client.put_branch_protection.assert_called_once()
    payload = client.put_branch_protection.call_args.args[1]
    assert payload["required_linear_history"] is True
    assert payload["required_pull_request_reviews"]["required_approving_review_count"] == 2


def test_apply_branch_sets_signed_commits_separately():
    client = MagicMock()
    client.get_branch_protection.return_value = None
    client.get_required_signatures.return_value = False
    config = _config(signed_commits=True)
    apply_branch(client, config, "main")
    client.set_required_signatures.assert_called_once_with("main", True)


def test_apply_branch_creates_ruleset_when_absent():
    client = MagicMock()
    client.find_ruleset_by_name.return_value = None
    config = _config(enforcement="ruleset", linear_history=True)
    result = apply_branch(client, config, "main")
    assert result.applied is True
    client.create_ruleset.assert_called_once()
    client.update_ruleset.assert_not_called()


def test_apply_branch_updates_existing_ruleset():
    client = MagicMock()
    client.find_ruleset_by_name.return_value = {"id": 7, "name": "repo-policy:main", "rules": []}
    config = _config(enforcement="ruleset", linear_history=True)
    result = apply_branch(client, config, "main")
    assert result.applied is True
    client.update_ruleset.assert_called_once()
    assert client.update_ruleset.call_args.args[0] == 7


def test_apply_all_applies_every_declared_branch():
    client = MagicMock()
    client.get_branch_protection.return_value = None
    client.get_required_signatures.return_value = False
    config = PolicyConfig(
        version=1, branches={"main": BranchPolicy(), "release": BranchPolicy(linear_history=True)}
    )
    results = apply_all(client, config)
    assert {r.branch for r in results} == {"main", "release"}


def test_prune_rulesets_deletes_only_orphaned_repo_policy_rulesets():
    client = MagicMock()
    client.list_rulesets.return_value = [
        {"id": 1, "name": "repo-policy:main"},
        {"id": 2, "name": "repo-policy:old-branch"},
        {"id": 3, "name": "someone-elses-ruleset"},
    ]
    config = _config()  # only "main" declared
    deleted = prune_rulesets(client, config)
    assert deleted == ["repo-policy:old-branch"]
    client.delete_ruleset.assert_called_once_with(2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_apply.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'repo_policy.apply'`

- [ ] **Step 3: Implement `apply.py`**

```python
# src/repo_policy/apply.py
from __future__ import annotations

from dataclasses import dataclass

from repo_policy.diff import Change, diff, resolve_desired
from repo_policy.github_client import GitHubClient
from repo_policy.models import BranchPolicy, PolicyConfig, effective_strict
from repo_policy.policies import branch_protection, rulesets


@dataclass
class BranchResult:
    branch: str
    changes: list[Change]
    applied: bool


def fetch_current(
    client: GitHubClient, branch: str, enforcement: str
) -> tuple[BranchPolicy, dict | None, int | None]:
    if enforcement == "branch_protection":
        raw = client.get_branch_protection(branch)
        signed = client.get_required_signatures(branch)
        return branch_protection.from_api(raw, signed_commits=signed), raw, None
    raw = client.find_ruleset_by_name(rulesets.ruleset_name(branch))
    ruleset_id = raw["id"] if raw else None
    return rulesets.from_api(raw), raw, ruleset_id


def plan_branch(client: GitHubClient, config: PolicyConfig, branch: str) -> tuple[list[Change], BranchPolicy]:
    desired = config.branches[branch]
    current, _raw, _ruleset_id = fetch_current(client, branch, desired.enforcement)
    resolved = resolve_desired(desired, current, strict=effective_strict(config, branch))
    return diff(resolved, current), resolved


def apply_branch(client: GitHubClient, config: PolicyConfig, branch: str) -> BranchResult:
    desired = config.branches[branch]
    current, raw, ruleset_id = fetch_current(client, branch, desired.enforcement)
    resolved = resolve_desired(desired, current, strict=effective_strict(config, branch))
    changes = diff(resolved, current)

    if not changes:
        return BranchResult(branch=branch, changes=[], applied=False)

    if desired.enforcement == "branch_protection":
        payload = branch_protection.to_api_payload(resolved, raw)
        client.put_branch_protection(branch, payload)
        if resolved.signed_commits != current.signed_commits:
            client.set_required_signatures(branch, bool(resolved.signed_commits))
    else:
        payload = rulesets.to_api_payload(branch, resolved)
        if ruleset_id is None:
            client.create_ruleset(payload)
        else:
            client.update_ruleset(ruleset_id, payload)

    return BranchResult(branch=branch, changes=changes, applied=True)


def apply_all(client: GitHubClient, config: PolicyConfig) -> list[BranchResult]:
    return [apply_branch(client, config, branch) for branch in config.branches]


def prune_rulesets(client: GitHubClient, config: PolicyConfig) -> list[str]:
    """Strict-mode only, gated by the top-level `strict` default (a removed branch has no
    per-branch setting left to consult). Deletes only rulesets matching the `repo-policy:` naming
    convention whose branch is no longer declared — never touches anything else."""
    declared_names = {rulesets.ruleset_name(branch) for branch in config.branches}
    deleted: list[str] = []
    for summary in client.list_rulesets():
        name = summary["name"]
        if name.startswith("repo-policy:") and name not in declared_names:
            client.delete_ruleset(summary["id"])
            deleted.append(name)
    return deleted
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_apply.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/repo_policy/apply.py tests/test_apply.py
git commit -m "feat: add apply engine with managed-scope and prune support"
```

---

### Task 12: Audit orchestration

**Files:**
- Create: `src/repo_policy/audit.py`
- Test: `tests/test_audit.py`

**Interfaces:**
- Consumes: `plan_branch` (Task 11), `Change` (Task 10), `PolicyConfig` (Task 2).
- Produces: `AuditResult(branch: str, changes: list[Change])` with `.compliant: bool` property, `audit_all(client, config) -> list[AuditResult]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_audit.py
from unittest.mock import MagicMock

from repo_policy.audit import audit_all
from repo_policy.models import BranchPolicy, PolicyConfig, PullRequestPolicy


def test_audit_all_reports_compliant_when_no_drift():
    client = MagicMock()
    client.get_branch_protection.return_value = None
    client.get_required_signatures.return_value = False
    config = PolicyConfig(version=1, branches={"main": BranchPolicy()})
    results = audit_all(client, config)
    assert len(results) == 1
    assert results[0].compliant is True
    assert results[0].changes == []


def test_audit_all_reports_drift():
    client = MagicMock()
    client.get_branch_protection.return_value = None
    client.get_required_signatures.return_value = False
    config = PolicyConfig(
        version=1,
        branches={"main": BranchPolicy(pull_requests=PullRequestPolicy(required=True, approvals=1, code_owner_review=False))},
    )
    results = audit_all(client, config)
    assert results[0].compliant is False
    assert len(results[0].changes) == 1


def test_audit_all_covers_every_declared_branch():
    client = MagicMock()
    client.get_branch_protection.return_value = None
    client.get_required_signatures.return_value = False
    config = PolicyConfig(version=1, branches={"main": BranchPolicy(), "release": BranchPolicy()})
    results = audit_all(client, config)
    assert {r.branch for r in results} == {"main", "release"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_audit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'repo_policy.audit'`

- [ ] **Step 3: Implement `audit.py`**

```python
# src/repo_policy/audit.py
from __future__ import annotations

from dataclasses import dataclass

from repo_policy.apply import plan_branch
from repo_policy.diff import Change
from repo_policy.github_client import GitHubClient
from repo_policy.models import PolicyConfig


@dataclass
class AuditResult:
    branch: str
    changes: list[Change]

    @property
    def compliant(self) -> bool:
        return not self.changes


def audit_all(client: GitHubClient, config: PolicyConfig) -> list[AuditResult]:
    results = []
    for branch in config.branches:
        changes, _resolved = plan_branch(client, config, branch)
        results.append(AuditResult(branch=branch, changes=changes))
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_audit.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/repo_policy/audit.py tests/test_audit.py
git commit -m "feat: add audit orchestration"
```

---

### Task 13: Plan rendering

**Files:**
- Create: `src/repo_policy/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `Change` (Task 10).
- Produces: `render_plan(repo: str, branch: str, changes: list[Change]) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_render.py
from repo_policy.diff import Change
from repo_policy.render import render_plan


def test_render_plan_reports_no_changes():
    output = render_plan("acme/widgets", "main", [])
    assert "Repository: acme/widgets" in output
    assert "Branch: main" in output
    assert "No changes required." in output


def test_render_plan_shows_symbols_per_action():
    changes = [
        Change(field="linear_history", current_value=False, desired_value=True, action="add"),
        Change(field="allow_force_push", current_value=True, desired_value=False, action="remove"),
        Change(field="pull_requests", current_value="1 approval", desired_value="2 approvals", action="modify"),
    ]
    output = render_plan("acme/widgets", "main", changes)
    assert "+ Linear history" in output
    assert "- Force pushes" in output
    assert "~ Pull request requirements" in output
    assert "3 changes required." in output


def test_render_plan_singular_change_count():
    changes = [Change(field="linear_history", current_value=False, desired_value=True, action="add")]
    output = render_plan("acme/widgets", "main", changes)
    assert "1 change required." in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'repo_policy.render'`

- [ ] **Step 3: Implement `render.py`**

```python
# src/repo_policy/render.py
from __future__ import annotations

from repo_policy.diff import Change

_SYMBOLS = {"add": "+", "modify": "~", "remove": "-"}

_LABELS = {
    "pull_requests": "Pull request requirements",
    "status_checks": "Required status checks",
    "signed_commits": "Signed commits",
    "linear_history": "Linear history",
    "allow_force_push": "Force pushes",
    "allow_deletion": "Branch deletion",
}


def render_plan(repo: str, branch: str, changes: list[Change]) -> str:
    changed_fields = {change.field for change in changes}
    lines = [f"Repository: {repo}", f"Branch: {branch}", ""]

    for field, label in _LABELS.items():
        if field not in changed_fields:
            lines.append(f"✓ {label}")

    for change in changes:
        symbol = _SYMBOLS[change.action]
        label = _LABELS[change.field]
        lines.append(f"{symbol} {label:<28} {change.current_value} → {change.desired_value}")

    lines.append("")
    if not changes:
        lines.append("No changes required.")
    else:
        noun = "change" if len(changes) == 1 else "changes"
        lines.append(f"{len(changes)} {noun} required.")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_render.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/repo_policy/render.py tests/test_render.py
git commit -m "feat: add human-readable plan rendering"
```

---

### Task 14: CLI

**Files:**
- Create: `src/repo_policy/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_policy`/`ConfigError` (Task 3), `GitHubClient`/`GitHubAPIError` (Task 4-6), `audit_all` (Task 12), `apply_all`/`prune_rulesets` (Task 11), `render_plan` (Task 13).
- Produces: `main` (Click group, the `repo-policy` console-script entry point) with `validate`, `audit`, `plan`, `apply` subcommands; exit codes per the Global Constraints table.

- [ ] **Step 1: Create a fixture for a branch with no declared requirements**

```yaml
# tests/fixtures/policy_no_requirements.yml
version: 1

branches:
  main: {}
```

This branch has every field unset, so managed-scope always resolves it against whatever the
live repo already has — it's compliant by construction, which is what the "audit is compliant"
test below needs (`policy_valid.yml` declares real requirements, so it's never compliant against
a bare mocked repo).

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_cli.py
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'repo_policy.cli'`

- [ ] **Step 4: Implement `cli.py`**

```python
# src/repo_policy/cli.py
from __future__ import annotations

import os
import subprocess
import sys

import click

from repo_policy.apply import apply_all, prune_rulesets
from repo_policy.audit import audit_all
from repo_policy.config import ConfigError, load_policy
from repo_policy.github_client import GitHubAPIError, GitHubClient
from repo_policy.render import render_plan

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_CONFIG_ERROR = 2
EXIT_API_ERROR = 3


def _resolve_token(token: str | None) -> str:
    return token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""


def _resolve_repo(repo: str | None) -> str:
    if repo:
        return repo
    env_repo = os.environ.get("GITHUB_REPOSITORY")
    if env_repo:
        return env_repo
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"], capture_output=True, text=True, check=False
    )
    url = result.stdout.strip()
    if url.endswith(".git"):
        url = url[: -len(".git")]
    for separator in ("github.com:", "github.com/"):
        if separator in url:
            return url.split(separator, 1)[1]
    raise click.ClickException("could not determine repository; pass --repo owner/name")


@click.group()
def main() -> None:
    """repo-policy: declarative GitHub repository governance."""


@main.command()
@click.option("--config", "config_path", default="policy.yml", show_default=True)
def validate(config_path: str) -> None:
    try:
        load_policy(config_path)
    except ConfigError as exc:
        click.echo(str(exc), err=True)
        sys.exit(EXIT_CONFIG_ERROR)
    click.echo(f"{config_path} is valid.")
    sys.exit(EXIT_OK)


def _run_check(config_path: str, repo: str | None, token: str | None, *, render: bool) -> int:
    try:
        config = load_policy(config_path)
    except ConfigError as exc:
        click.echo(str(exc), err=True)
        return EXIT_CONFIG_ERROR

    resolved_repo = _resolve_repo(repo)
    owner, name = resolved_repo.split("/", 1)

    try:
        with GitHubClient(token=_resolve_token(token), owner=owner, repo=name) as client:
            results = audit_all(client, config)
    except GitHubAPIError as exc:
        click.echo(str(exc), err=True)
        return EXIT_API_ERROR

    any_drift = False
    for result in results:
        if render:
            click.echo(render_plan(resolved_repo, result.branch, result.changes))
        elif not result.compliant:
            click.echo(f"{result.branch}: {len(result.changes)} change(s) required")
        any_drift = any_drift or not result.compliant

    if not any_drift and not render:
        click.echo(f"{resolved_repo} is compliant.")
    return EXIT_DRIFT if any_drift else EXIT_OK


@main.command()
@click.option("--config", "config_path", default="policy.yml", show_default=True)
@click.option("--repo", default=None)
@click.option("--token", default=None)
def audit(config_path: str, repo: str | None, token: str | None) -> None:
    sys.exit(_run_check(config_path, repo, token, render=False))


@main.command()
@click.option("--config", "config_path", default="policy.yml", show_default=True)
@click.option("--repo", default=None)
@click.option("--token", default=None)
def plan(config_path: str, repo: str | None, token: str | None) -> None:
    sys.exit(_run_check(config_path, repo, token, render=True))


@main.command()
@click.option("--config", "config_path", default="policy.yml", show_default=True)
@click.option("--repo", default=None)
@click.option("--token", default=None)
def apply(config_path: str, repo: str | None, token: str | None) -> None:
    try:
        config = load_policy(config_path)
    except ConfigError as exc:
        click.echo(str(exc), err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    resolved_repo = _resolve_repo(repo)
    owner, name = resolved_repo.split("/", 1)

    try:
        with GitHubClient(token=_resolve_token(token), owner=owner, repo=name) as client:
            results = apply_all(client, config)
            if config.strict:
                for deleted_name in prune_rulesets(client, config):
                    click.echo(f"- removed orphaned ruleset {deleted_name}")
    except GitHubAPIError as exc:
        click.echo(str(exc), err=True)
        sys.exit(EXIT_API_ERROR)

    for result in results:
        if result.applied:
            click.echo(f"{result.branch}: applied {len(result.changes)} change(s)")
        else:
            click.echo(f"{result.branch}: no changes needed")
    sys.exit(EXIT_OK)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS (8 tests)

- [ ] **Step 6: Run the full test suite**

Run: `python -m pytest -v`
Expected: PASS (all tests from Tasks 1-14)

- [ ] **Step 7: Commit**

```bash
git add src/repo_policy/cli.py tests/test_cli.py tests/fixtures/policy_no_requirements.yml
git commit -m "feat: add repo-policy CLI with validate/audit/plan/apply"
```

---

### Task 15: Idempotency integration test

**Files:**
- Create: `tests/test_idempotency.py`

**Interfaces:**
- Consumes: `apply_all` (Task 11), `PolicyConfig`/`BranchPolicy`/`PullRequestPolicy`/`StatusChecksPolicy` (Task 2).

This is the test that directly validates the spec's core requirement (§7 / the README's "Critical design requirement"): applying an already-compliant policy must issue zero mutating HTTP calls on the second run.

- [ ] **Step 1: Write the test**

```python
# tests/test_idempotency.py
from unittest.mock import MagicMock

from repo_policy.apply import apply_all
from repo_policy.models import BranchPolicy, PolicyConfig, PullRequestPolicy, StatusChecksPolicy


def test_apply_twice_against_already_compliant_repo_makes_zero_mutating_calls():
    config = PolicyConfig(
        version=1,
        branches={
            "main": BranchPolicy(
                pull_requests=PullRequestPolicy(required=True, approvals=2, code_owner_review=True),
                status_checks=StatusChecksPolicy(required=["build", "test"]),
                signed_commits=True,
                linear_history=True,
                allow_force_push=False,
                allow_deletion=False,
            )
        },
    )

    client = MagicMock()
    # First call: nothing exists yet.
    client.get_branch_protection.return_value = None
    client.get_required_signatures.return_value = False

    first_results = apply_all(client, config)
    assert first_results[0].applied is True
    client.put_branch_protection.assert_called_once()
    put_payload = client.put_branch_protection.call_args.args[1]
    client.set_required_signatures.assert_called_once_with("main", True)

    # Second call: the mock now reflects exactly what the first apply wrote.
    client.reset_mock()
    client.get_branch_protection.return_value = put_payload
    client.get_required_signatures.return_value = True

    second_results = apply_all(client, config)
    assert second_results[0].applied is False
    assert second_results[0].changes == []
    client.put_branch_protection.assert_not_called()
    client.set_required_signatures.assert_not_called()
    client.create_ruleset.assert_not_called()
    client.update_ruleset.assert_not_called()
    client.delete_ruleset.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails or passes for the right reason**

Run: `python -m pytest tests/test_idempotency.py -v`
Expected: PASS — every module it depends on already exists from Tasks 1-14. If this fails, it means `to_api_payload`'s output doesn't round-trip through `from_api` back to an equal `BranchPolicy`; fix the mismatched translator before proceeding (this test is the source of truth for that round-trip).

- [ ] **Step 3: Commit**

```bash
git add tests/test_idempotency.py
git commit -m "test: add idempotency guarantee for apply"
```

---

### Task 16: GitHub Action (Docker container action)

**Files:**
- Create: `Dockerfile`
- Create: `action.yml`
- Create: `src/repo_policy/entrypoint.py`

**Interfaces:**
- Consumes: `main` (Task 14, the Click group), reads `INPUT_CONFIG`, `INPUT_MODE`, `GITHUB_TOKEN`, `GITHUB_REPOSITORY` from the Actions runtime environment.

- [ ] **Step 1: Create the entrypoint script**

```python
# src/repo_policy/entrypoint.py
"""Translates GitHub Actions `with:` inputs (INPUT_* env vars) into repo-policy CLI args."""
from __future__ import annotations

import os
import sys

from repo_policy.cli import main


def run() -> None:
    config_path = os.environ.get("INPUT_CONFIG", ".github/repository-policy.yml")
    mode = os.environ.get("INPUT_MODE", "audit")
    if mode not in {"validate", "audit", "plan", "apply"}:
        print(f"::error::unsupported mode '{mode}' — expected validate, audit, plan, or apply", file=sys.stderr)
        sys.exit(2)
    sys.argv = ["repo-policy", mode, "--config", config_path]
    main()


if __name__ == "__main__":
    run()
```

- [ ] **Step 2: Create the Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

ENTRYPOINT ["python", "-m", "repo_policy.entrypoint"]
```

- [ ] **Step 3: Create `action.yml`**

```yaml
name: "repo-policy"
description: "Declarative GitHub repository governance — audit, plan, or apply a policy.yml."
branding:
  icon: "shield"
  color: "blue"

inputs:
  config:
    description: "Path to the policy YAML file, relative to the repo root."
    required: false
    default: ".github/repository-policy.yml"
  mode:
    description: "One of: validate, audit, plan, apply."
    required: false
    default: "audit"

runs:
  using: "docker"
  image: "Dockerfile"
```

- [ ] **Step 4: Verify the image builds**

Run: `docker build -t repo-policy:test .`
Expected: image builds successfully with no errors.

- [ ] **Step 5: Verify the entrypoint runs against a fixture config**

Run: `docker run --rm -e INPUT_CONFIG=tests/fixtures/policy_valid.yml -e INPUT_MODE=validate -v "$(pwd)":/app repo-policy:test`
Expected: prints `tests/fixtures/policy_valid.yml is valid.` and exits 0.

- [ ] **Step 6: Commit**

```bash
git add Dockerfile action.yml src/repo_policy/entrypoint.py
git commit -m "feat: add GitHub Action (Docker container action)"
```

---

### Task 17: CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- None (CI-only; consumes the Task 1 `pyproject.toml` dev extras).

- [ ] **Step 1: Create the workflow**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  pull_request:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: ruff check src tests
      - run: mypy src
      - run: pytest -v
```

- [ ] **Step 2: Verify locally**

Run: `pip install -e ".[dev]" && ruff check src tests && mypy src && pytest -v`
Expected: all three commands exit 0.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add test/lint/typecheck workflow"
```

---

### Task 18: Release automation

**Files:**
- Modify: `pyproject.toml`
- Create: `.github/workflows/release.yml`

**Interfaces:**
- None (release-only; reads Conventional Commits history on `main`).

- [ ] **Step 1: Add `python-semantic-release` config to `pyproject.toml`**

Append to `pyproject.toml`:

```toml
[tool.semantic_release]
version_toml = ["pyproject.toml:project.version"]
branch = "main"
build_command = "pip install build && python -m build"
commit_message = "chore(release): {version} [skip ci]"

[tool.semantic_release.changelog]
changelog_file = "CHANGELOG.md"
```

- [ ] **Step 2: Create the release workflow**

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    branches: [main]

permissions:
  contents: write
  id-token: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GITHUB_TOKEN }}

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Python Semantic Release
        id: release
        uses: python-semantic-release/python-semantic-release@v9
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}

      - name: Publish to PyPI
        if: steps.release.outputs.released == 'true'
        uses: pypa/gh-action-pypi-publish@release/v1

      - name: Move floating major tag
        if: steps.release.outputs.released == 'true'
        run: |
          MAJOR_TAG="v$(echo '${{ steps.release.outputs.tag }}' | sed -E 's/^v([0-9]+)\..*/\1/')"
          git tag -f "$MAJOR_TAG" "${{ steps.release.outputs.tag }}"
          git push origin "$MAJOR_TAG" --force
```

- [ ] **Step 3: Document the commit convention**

Confirm `CONTRIBUTING.md` (Task 19) states that commit messages must follow Conventional Commits (`feat:`, `fix:`, `chore:`, etc.) since `python-semantic-release` derives version bumps from them — this workflow has no effect otherwise.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml .github/workflows/release.yml
git commit -m "ci: add semantic-release automation with floating major tag"
```

---

### Task 19: Documentation

**Files:**
- Modify: `README.md`
- Create: `CONTRIBUTING.md`
- Create: `SECURITY.md`

**Interfaces:** None (docs only).

- [ ] **Step 1: Write `README.md`**

```markdown
# repo-policy

Lightweight, declarative repository governance for GitHub. Define expected branch protection
and ruleset configuration in YAML; audit, preview, and apply it locally or in CI.

Not a Terraform replacement — no state file, no backend. `repo-policy` is safe to adopt
incrementally on a live repository: by default it only ever touches branches you declare, and
never deletes anything you didn't ask it to manage.

## Install

\`\`\`bash
pip install repo-policy
\`\`\`

## Quick start

\`\`\`yaml
# policy.yml
version: 1

branches:
  main:
    pull_requests:
      required: true
      approvals: 2
      code_owner_review: true
    status_checks:
      required: [build, test]
    signed_commits: true
    linear_history: true
    allow_force_push: false
    allow_deletion: false
\`\`\`

\`\`\`bash
repo-policy validate
repo-policy audit --repo acme/widgets
repo-policy plan --repo acme/widgets
repo-policy apply --repo acme/widgets
\`\`\`

## GitHub Action

\`\`\`yaml
- uses: shipsolid/repo-policy@v1
  with:
    config: .github/repository-policy.yml
    mode: audit
\`\`\`

## How it works

Every declared branch is diffed against live GitHub state and reconciled through one of two
backends, selected per branch with `enforcement: branch_protection | ruleset` (default
`branch_protection`). See [the design spec](docs/superpowers/specs/2026-09-19-repo-policy-design.md)
for the full schema, safety model, and known v1 limitations.

## Exit codes

| Code | Meaning |
| ---- | ------- |
| 0 | Success / compliant / no-op |
| 1 | Drift detected (`audit`/`plan`) |
| 2 | Invalid `policy.yml` |
| 3 | GitHub API or auth error |

## License

MIT
```

- [ ] **Step 2: Write `CONTRIBUTING.md`**

```markdown
# Contributing

## Setup

\`\`\`bash
pip install -e ".[dev]"
\`\`\`

## Before opening a PR

\`\`\`bash
ruff check src tests
mypy src
pytest -v
\`\`\`

## Commit messages

This project uses [Conventional Commits](https://www.conventionalcommits.org/) — releases and
version bumps are automated by `python-semantic-release` from commit history:

- `feat: ...` → minor version bump
- `fix: ...` → patch version bump
- `feat!: ...` or a `BREAKING CHANGE:` footer → major version bump
- `chore:`, `docs:`, `test:`, `ci:` → no release

## Adding a new policy field

1. Add the field to the relevant model in `src/repo_policy/models.py`.
2. Add it to `_FIELDS` and `_SCHEMA_DEFAULTS` in `src/repo_policy/diff.py`.
3. Map it to both backends in `src/repo_policy/policies/branch_protection.py` and
   `src/repo_policy/policies/rulesets.py`.
4. Add the label to `_LABELS` in `src/repo_policy/render.py`.
5. Add coverage in each affected test file — the diff engine, both translators, and the
   idempotency test in `tests/test_idempotency.py`.
```

- [ ] **Step 3: Write `SECURITY.md`**

```markdown
# Security Policy

## Reporting a Vulnerability

Please report security issues privately via GitHub's
["Report a vulnerability"](https://github.com/shipsolid/repo-policy/security/advisories/new)
form rather than opening a public issue. We'll acknowledge within 5 business days.

## Scope

`repo-policy` requires a GitHub token with `repo` (or fine-grained `administration:write`)
permissions to manage branch protection and rulesets. Treat that token with the same care as any
credential capable of changing repository security settings. The tool never stores the token —
it is read once per invocation from `--token`, `GITHUB_TOKEN`, or `GH_TOKEN`.
```

- [ ] **Step 4: Commit**

```bash
git add README.md CONTRIBUTING.md SECURITY.md
git commit -m "docs: add README, CONTRIBUTING, and SECURITY"
```
