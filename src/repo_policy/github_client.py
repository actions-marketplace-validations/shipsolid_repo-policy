from __future__ import annotations

import time

import httpx


class GitHubAPIError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _expect_response(response: httpx.Response | None) -> httpx.Response:
    """_request() only returns None when called with allow_404=True; every call site below
    omits that flag, so None here means _request's contract was violated. Raising explicitly
    (rather than a bare assert, which python -O strips entirely) keeps that guarantee real."""
    if response is None:
        raise GitHubAPIError("GitHubClient._request unexpectedly returned no response")
    return response


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

    def __enter__(self) -> GitHubClient:  # noqa: PYI034 (Self needs Python 3.11+; we target 3.10+)
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        allow_404: bool = False,
    ) -> httpx.Response | None:
        attempt = 0
        while True:
            response = self._client.request(method, path, json=json, params=params)

            if response.status_code == 404 and allow_404:
                return None
            if response.status_code < 400:
                return response

            is_rate_limited = response.status_code == 429 or (
                response.status_code == 403 and "rate limit" in response.text.lower()
            )
            is_retryable = is_rate_limited or response.status_code >= 500

            if is_retryable and attempt < self._max_retries:
                time.sleep(self._backoff_seconds * (2**attempt))
                attempt += 1
                continue

            raise GitHubAPIError(
                f"GitHub API error {response.status_code} on {method} {path}: {response.text}",
                status_code=response.status_code,
            )

    def get_branch_protection(self, branch: str) -> dict | None:
        response = self._request(
            "GET", f"/repos/{self.owner}/{self.repo}/branches/{branch}/protection", allow_404=True
        )
        return response.json() if response is not None else None

    def put_branch_protection(self, branch: str, payload: dict) -> dict:
        response = self._request(
            "PUT", f"/repos/{self.owner}/{self.repo}/branches/{branch}/protection", json=payload
        )
        return _expect_response(response).json()

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

    def list_rulesets(self) -> list[dict]:
        results: list[dict] = []
        path: str | None = f"/repos/{self.owner}/{self.repo}/rulesets"
        params: dict | None = {"per_page": 100}
        while path is not None:
            response = _expect_response(self._request("GET", path, params=params))
            results.extend(response.json())
            next_link = response.links.get("next")
            path = next_link["url"] if next_link else None
            params = None  # the next-page URL already carries its own query string
        return results

    def get_ruleset(self, ruleset_id: int) -> dict:
        response = self._request("GET", f"/repos/{self.owner}/{self.repo}/rulesets/{ruleset_id}")
        return _expect_response(response).json()

    def find_ruleset_by_name(self, name: str, rulesets: list[dict] | None = None) -> dict | None:
        candidates = rulesets if rulesets is not None else self.list_rulesets()
        for summary in candidates:
            if summary["name"] == name:
                return self.get_ruleset(summary["id"])
        return None

    def create_ruleset(self, payload: dict) -> dict:
        response = self._request("POST", f"/repos/{self.owner}/{self.repo}/rulesets", json=payload)
        return _expect_response(response).json()

    def update_ruleset(self, ruleset_id: int, payload: dict) -> dict:
        response = self._request(
            "PUT", f"/repos/{self.owner}/{self.repo}/rulesets/{ruleset_id}", json=payload
        )
        return _expect_response(response).json()

    def delete_ruleset(self, ruleset_id: int) -> None:
        self._request("DELETE", f"/repos/{self.owner}/{self.repo}/rulesets/{ruleset_id}")
