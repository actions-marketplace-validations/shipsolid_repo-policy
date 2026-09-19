import httpx
import pytest
import respx

from repo_policy.github_client import GitHubAPIError, GitHubClient, _expect_response


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


@respx.mock
def test_request_retries_on_429_then_succeeds(client):
    route = respx.get("https://api.github.com/repos/acme/widgets/rate-limited")
    route.side_effect = [
        httpx.Response(429, json={"message": "You have exceeded a secondary rate limit"}),
        httpx.Response(200, json={"ok": True}),
    ]
    response = client._request("GET", "/repos/acme/widgets/rate-limited")
    assert response.json() == {"ok": True}
    assert route.call_count == 2


def test_expect_response_raises_explicit_error_on_none():
    with pytest.raises(GitHubAPIError, match="unexpectedly returned no response"):
        _expect_response(None)


def test_expect_response_returns_response_unchanged():
    response = httpx.Response(200, json={"ok": True})
    assert _expect_response(response) is response


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
    assert route.calls[0].request.content == b'{"enforce_admins":false}'


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


@respx.mock
def test_list_rulesets_returns_summaries(client):
    respx.get("https://api.github.com/repos/acme/widgets/rulesets").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "name": "repo-policy:main"}])
    )
    assert client.list_rulesets() == [{"id": 1, "name": "repo-policy:main"}]


@respx.mock
def test_list_rulesets_follows_pagination_link_header(client):
    next_url = "https://api.github.com/repos/acme/widgets/rulesets?per_page=100&page=2"
    route = respx.get("https://api.github.com/repos/acme/widgets/rulesets")
    route.side_effect = [
        httpx.Response(
            200,
            json=[{"id": 1, "name": "page-one"}],
            headers={"Link": f'<{next_url}>; rel="next"'},
        ),
        httpx.Response(200, json=[{"id": 2, "name": "page-two"}]),
    ]
    assert client.list_rulesets() == [{"id": 1, "name": "page-one"}, {"id": 2, "name": "page-two"}]
    assert route.call_count == 2


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
def test_find_ruleset_by_name_reuses_prefetched_list_without_a_new_get(client):
    list_route = respx.get("https://api.github.com/repos/acme/widgets/rulesets")
    respx.get("https://api.github.com/repos/acme/widgets/rulesets/1").mock(
        return_value=httpx.Response(200, json={"id": 1, "name": "repo-policy:main", "rules": []})
    )
    prefetched = [{"id": 1, "name": "repo-policy:main"}, {"id": 2, "name": "other"}]
    result = client.find_ruleset_by_name("repo-policy:main", rulesets=prefetched)
    assert result == {"id": 1, "name": "repo-policy:main", "rules": []}
    assert not list_route.called


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


@respx.mock
def test_get_repo(client):
    respx.get("https://api.github.com/repos/acme/widgets").mock(
        return_value=httpx.Response(200, json={"default_branch": "main", "delete_branch_on_merge": False})
    )
    data = client.get_repo()
    assert data["default_branch"] == "main"


@respx.mock
def test_update_repo_settings(client):
    route = respx.patch("https://api.github.com/repos/acme/widgets").mock(
        return_value=httpx.Response(200, json={"delete_branch_on_merge": True})
    )
    data = client.update_repo_settings({"delete_branch_on_merge": True})
    assert data["delete_branch_on_merge"] is True
    assert route.calls[0].request.content == b'{"delete_branch_on_merge":true}'


@respx.mock
def test_get_vulnerability_alerts_enabled(client):
    respx.get("https://api.github.com/repos/acme/widgets/vulnerability-alerts").mock(
        return_value=httpx.Response(204)
    )
    assert client.get_vulnerability_alerts() is True


@respx.mock
def test_get_vulnerability_alerts_disabled(client):
    respx.get("https://api.github.com/repos/acme/widgets/vulnerability-alerts").mock(
        return_value=httpx.Response(404)
    )
    assert client.get_vulnerability_alerts() is False


@respx.mock
def test_enable_vulnerability_alerts(client):
    route = respx.put("https://api.github.com/repos/acme/widgets/vulnerability-alerts").mock(
        return_value=httpx.Response(204)
    )
    client.enable_vulnerability_alerts()
    assert route.called
