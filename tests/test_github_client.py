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
