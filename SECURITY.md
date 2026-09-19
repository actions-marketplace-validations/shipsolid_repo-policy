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

**In GitHub Actions, this must be a real PAT stored as a repository secret — never the
automatically-generated `secrets.GITHUB_TOKEN`.** Confirmed against a real workflow run:
`GITHUB_TOKEN`'s permission scopes don't include repository administration under any
`permissions:` configuration, so it always fails with `403 Resource not accessible by
integration` on branch protection/ruleset endpoints, regardless of what the workflow grants it.

## Threat Model

| Actor | Attack Vector | Impact | Mitigation |
|---|---|---|---|
| Attacker with repo write access but not admin | Modify `policy.yml` to weaken branch protection (e.g. drop required approvals), merge it, wait for `apply` to run in CI | Branch protection silently weakened | Require review on changes to `policy.yml` itself via branch protection on the repo that runs repo-policy — repo-policy cannot protect its own config file from a compromised reviewer |
| Attacker who obtains the CI-stored PAT | Full read/write on whatever the PAT's scope covers — not limited to what `policy.yml` declares | Arbitrary branch protection/ruleset changes, or broader if the PAT has full `repo` scope | Scope the PAT as narrowly as GitHub allows (fine-grained PAT, `Administration` permission only, single-repository access); rotate it; never log it (repo-policy never prints the token) |
| Malicious `policy.yml` in a fork's PR, run via `pull_request_target` | Attacker-controlled config gets a privileged token via workflow misconfiguration | Same blast radius as PAT compromise above | Never run repo-policy's `apply` mode on `pull_request_target` against untrusted input; `audit`/`plan` read-only are lower risk but still exercise real API calls with the token |
| Naming collision: something else creates a ruleset named `repo-policy:<branch>` | `strict` mode's prune logic would treat it as repo-policy-owned and could delete it | Loss of an unrelated ruleset | The naming convention is a documented hard constraint (see `docs/adrs/0004-*`) — don't create rulesets with that prefix outside repo-policy |

## Authentication

repo-policy authenticates to the GitHub REST API with a single bearer token, resolved in order
from `--token`, `GITHUB_TOKEN`, then `GH_TOKEN` (`cli._resolve_token`). There is no OAuth flow, no
session, and no credential caching — the token lives only in the process's memory for the
duration of one invocation.

## Authorization

repo-policy performs no authorization of its own; it relies entirely on GitHub's own permission
model for the token it's given. Whatever the token can do, repo-policy can do — it does not
restrict itself to a subset. This is why token scoping (above) is the primary control.

## Secrets Management

- The token is never written to disk, logged, or included in any error message.
- `policy.yml` is not an appropriate place to store secrets and repo-policy never expects one
  there — it contains only declarative policy, no credentials.
- In CI, store the PAT as an encrypted repository (or organization) secret; never as a plaintext
  workflow env default or a committed file.
- A second, narrower-scoped PAT (`REPO_POLICY_E2E_TOKEN`) exists for the automated E2E suite
  (`tests/e2e/`, `.github/workflows/e2e.yml`): fine-grained, `Administration: Read and write`,
  restricted to the single disposable fixture repo (`shipsolid/repo-policy-e2e-fixture`). Its
  blast radius is bounded to that one repo — a concrete instance of the "scope the PAT as
  narrowly as GitHub allows" mitigation already listed in the Threat Model below, not a new
  category of risk.

## Vulnerability Management

This project has no automated dependency-vulnerability scanning configured yet (see
`docs/ci-cd.md` / `ROADMAP.md`). Dependency upper bounds are pinned in `pyproject.toml` to reduce
the blast radius of an unreviewed transitive upgrade, but that is not a substitute for scanning.

## Security Baseline

- Dependencies pinned with upper bounds (`pyproject.toml`).
- PyPI publishing uses trusted publishing (OIDC) — no long-lived PyPI API token stored anywhere.
- No secrets, tokens, or credentials are ever persisted by repo-policy itself.

## Known Limitations

- No mTLS or certificate-based auth path — token-based auth only.
- No built-in secret scanning of `policy.yml` — a user could technically put a secret in a custom
  field extension in the future; the current schema has no such field, so this is currently moot.
- See the Threat Model above for the PAT-scope and `policy.yml`-review gaps, which are
  organizational controls repo-policy cannot enforce on your behalf.
