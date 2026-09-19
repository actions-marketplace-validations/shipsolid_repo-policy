---
adr: 0001
title: Use httpx directly instead of PyGithub for the GitHub API client
status: accepted
date: 2026-09-19
deciders: Amit Singh
domain: platform
---

## Context

repo-policy needs to call two related but distinct parts of the GitHub REST API: classic branch
protection (a long-stable API) and repository rulesets (a newer API surface, still evolving). The
client needed full control over request/response shape, retry behavior, and pagination.

## Decision

Talk to the GitHub REST API directly via `httpx`, with a small hand-written client
(`github_client.py`) rather than a wrapper library.

## Alternatives Considered

- **PyGithub** — the most widely used Python GitHub client. Rejected: at the time of this
  decision its Rulesets support was partial and newer than the raw REST API, which would have
  forced a mixed approach (PyGithub for branch protection, raw HTTP for rulesets) anyway — better
  to have one consistent client for both.
- **ghapi** — thinner than PyGithub, but still an extra abstraction layer with its own release
  cadence, for a client this small (six methods) doesn't pay for itself.

## Consequences

- Full control over retry/backoff logic tuned to what GitHub actually returns (429, 403 with
  rate-limit text, 5xx) — verified against a real repo, see `docs/test-strategy.md`.
- repo-policy owns the exact request/response shape for every endpoint, so a field-name mismatch
  is a repo-policy bug, not a wrapper-library staleness problem.
- Cost: repo-policy re-implements pagination and header handling that a wrapper library would
  otherwise provide — a small, one-time cost paid once in `github_client.py`.

## Links

- `src/repo_policy/github_client.py`
- `docs/test-strategy.md` (429/pagination test cases)
