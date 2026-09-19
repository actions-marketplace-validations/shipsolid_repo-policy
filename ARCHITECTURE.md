# Architecture

## Purpose

`repo-policy` lets a team declare the expected state of GitHub branch protection and repository
rulesets in one YAML file, then reconcile a real repository against it — locally, in CI, or via
the shipped GitHub Action. It exists so that "what does our branch protection require" is a
reviewable, version-controlled file instead of a fact locked inside GitHub's settings UI.

## System Context (C4 L1)

```
                     ┌──────────────────────┐
  developer /   ────▶│                      │
  CI workflow        │      repo-policy     │────▶  GitHub REST API
                      │    (CLI / Action)    │       (branch protection,
  policy.yml    ────▶│                      │        repository rulesets)
                     └──────────────────────┘
```

repo-policy has exactly one external dependency: the GitHub REST API. It reads `policy.yml` from
local disk and a GitHub token from `--token`/`GITHUB_TOKEN`/`GH_TOKEN`; it has no database, no
state file, and no other network dependency.

## Container / Component View (C4 L2/L3)

```
src/repo_policy/
├── cli.py                 Click entry point — validate / audit / plan / apply, exit codes
├── config.py               policy.yml -> PolicyConfig (Pydantic), ConfigError on failure
├── models.py                PolicyConfig / BranchPolicy / PullRequestPolicy / StatusChecksPolicy
├── github_client.py         httpx wrapper: auth headers, retry/backoff, pagination
├── diff.py                   resolve_desired() + diff(): the one diff engine every command shares
├── apply.py                   orchestration: fetch_current / plan_branch / apply_branch /
│                              apply_all / prune_rulesets / prefetch_rulesets
├── audit.py                   read-only wrapper around apply.plan_branch, for audit/plan
├── render.py                   human-readable +/-/~/✓ diff rendering for `plan`
├── entrypoint.py               GitHub Actions INPUT_* env vars -> CLI argv, for the Docker Action
├── repo_settings.py            orchestration for the repo-wide repo_settings section:
│                                plan_repo_settings / apply_repo_settings
└── policies/
    ├── pull_requests.py       PullRequestPolicy <-> branch-protection JSON <-> ruleset rule JSON
    ├── status_checks.py       StatusChecksPolicy <-> branch-protection JSON <-> ruleset rule JSON
    ├── branch_protection.py   full BranchPolicy <-> classic branch-protection payload
    ├── rulesets.py            full BranchPolicy <-> repository-ruleset payload
    └── repo_settings.py       RepoSettingsPolicy <-> 3 different GitHub endpoint shapes
                                (flat PATCH, nested security_and_analysis PATCH, 3 independent
                                GET/PUT toggle endpoints)
```

`cli.py` is the only module that knows about Click, exit codes, or environment variables — every
other module is a plain, independently testable function library. `pull_requests.py` and
`status_checks.py` are shared between the two backends specifically so a policy field's meaning
can't drift between "branch protection" and "ruleset" mode.

## Domain Model

- **`PolicyConfig`** — the whole `policy.yml`: a schema `version`, a top-level `strict` default,
  and a `branches: dict[str, BranchPolicy]` map.
- **`BranchPolicy`** — one branch's desired state: `enforcement` (`branch_protection` | `ruleset`,
  default `branch_protection`), an optional per-branch `strict` override, and eleven *optional*
  policy fields (`pull_requests`, `status_checks`, `signed_commits`, `linear_history`,
  `allow_force_push`, `allow_deletion`, `enforce_admins`, `required_conversation_resolution`,
  `lock_branch`, `allow_fork_syncing`, `clear_restrictions`). `None` on any of these eleven means
  "not declared" — this is the single most important modeling choice in the codebase (see
  `docs/adrs/0003-*`). Five of them have no GitHub Rulesets equivalent (the four from Phase 1 —
  `required_conversation_resolution`'s nearest cousin, `required_review_thread_resolution`, only
  exists as a `pull_request` rule parameter, which doesn't always exist — plus `clear_restrictions`,
  since GitHub Rulesets has no `restrictions`-equivalent concept at all) — a model validator on
  `BranchPolicy` rejects declaring a non-permissive value for any of them on a branch with
  `enforcement: ruleset` at `validate` time, while still allowing the permissive (no-op) value
  through so the same type can represent live ruleset state internally. `PullRequestPolicy`
  additionally carries `dismiss_stale_reviews`/`require_last_push_approval`, which *are* fully
  cross-backend.
- **`PullRequestPolicy`** / **`StatusChecksPolicy`** — the two fields whose desired state is more
  than a boolean.
- **`RepoSettingsPolicy`** — an optional, repo-wide (not per-branch) section: `delete_branch_on_merge`,
  `allow_update_branch`, `vulnerability_alerts`, `automated_security_fixes`,
  `private_vulnerability_reporting`, `secret_scanning`, `secret_scanning_push_protection`. `None`
  on any field means "not declared" (same modeling choice as `BranchPolicy`), and the whole section
  can be `None` (not declared at all) — the most common case for every `policy.yml` written before
  this feature existed, which makes zero repo-settings API calls. Unlike branch-level fields,
  `repo_settings` does **not** participate in `strict` mode — there's no universal "permissive
  baseline" that would be safe to auto-apply for e.g. `delete_branch_on_merge`, so this section is
  managed-scope only, always. `automated_security_fixes: true` requires `vulnerability_alerts: true`
  to also be declared — enforced by a model validator, since GitHub rejects enabling Dependabot
  security updates before Dependabot alerts.
- **Current state** is the *same* `BranchPolicy` type, populated by `branch_protection.from_api()`
  or `rulesets.from_api()` from a live GitHub API response — so `diff()` always compares two
  instances of one type, never a raw dict against a model. A branch with nothing configured
  normalizes to a fully permissive `BranchPolicy`, never to inconsistent `None`s.
- **`Change`** (in `diff.py`) — one field's `(current_value, desired_value, action)`, where
  `action` is `add` / `modify` / `remove`. This is the one artifact `audit`, `plan`, and `apply`
  all consume — there is no separate diff logic per command.

## Data Flow

1. `config.load_policy()` parses `policy.yml` into a `PolicyConfig`, or raises `ConfigError`
   (exit 2).
2. For each declared branch, `apply.fetch_current()` calls the matching backend's `from_api()`
   against a live GitHub API response, producing a `BranchPolicy` representing current reality.
3. `diff.resolve_desired()` merges the declared `BranchPolicy` against current state: an unset
   field inherits *current's* value in managed-scope (default), or the schema's permissive default
   in `strict` mode. The result, `resolved`, always has every field concretely set.
4. `diff.diff(resolved, current)` produces the `Change` list — empty means compliant.
5. `audit`/`plan` stop here (read-only) and report; `apply` additionally calls the matching
   backend's `to_api_payload()` and issues exactly one mutating API call per branch that actually
   changed — zero calls when the `Change` list is empty. This is what makes `apply` idempotent:
   rerun it against an already-compliant repo and it makes no network writes at all.

## Sequence: `repo-policy apply` (one ruleset-enforced branch)

```
CLI            config.py       apply.py                     github_client.py       GitHub API
 │  apply         │                │                              │                    │
 │───load_policy─▶│                │                              │                    │
 │◀──PolicyConfig─│                │                              │                    │
 │───────────────── apply_all(client, config) ───────────────────▶│                    │
 │                │           prefetch_rulesets() ─────────────────▶ list_rulesets() ──▶│ GET /rulesets
 │                │                │                              │◀──── 200, [...] ───│
 │                │           fetch_current(branch) ────────────────▶ find_ruleset_by_name()
 │                │                │                              │   (uses the prefetched list —
 │                │                │                              │    no extra GET per branch)
 │                │           resolve_desired() + diff() — empty? skip API call, done
 │                │                │                              │
 │                │           (non-empty) to_api_payload() ─────────▶ update_ruleset() ───▶│ PUT /rulesets/{id}
 │                │                │                              │◀──────── 200 ─────────│
 │◀─────────────────── BranchResult(applied=True) ─────────────────│                    │
```

## Integration Architecture

| External system | Direction | Protocol | Auth | Failure/timeout behavior |
|---|---|---|---|---|
| GitHub REST API | outbound only | HTTPS / JSON (`X-GitHub-Api-Version: 2022-11-28`) | `Authorization: Bearer <token>` | 30s timeout; retries 429, 403-with-rate-limit-text, and 5xx with exponential backoff (`github_client._request`), up to 3 attempts; anything else raises `GitHubAPIError` immediately |

There is no other integration. repo-policy does not call PyPI at runtime, does not phone home, and
does not persist state outside the process it runs in.

## Apply Safety Model (managed-scope vs. strict)

- **Managed-scope (default):** `apply` never touches a branch absent from `policy.yml`. Within a
  declared branch, only the fields present in `policy.yml` are enforced; everything else — for
  `branch_protection`, this now only includes the status-check `strict` field, the one GitHub
  setting the v1 schema still doesn't model at all (`restrictions` became modeled via
  `clear_restrictions`, though only as "null or leave alone," not an arbitrary allowlist — see the
  Domain Model section above) — is read from current state and passed straight through, never
  reset. For `ruleset`, the tool only ever creates/reads/updates a ruleset named
  `repo-policy:<branch>`; it never inspects or modifies any other ruleset.
- **Strict (`strict: true`, top-level default or per-branch override — branch wins):** within a
  *declared* branch, fields left unset are now actively reset to the permissive schema default
  instead of left alone. For `ruleset` only, strict additionally deletes any `repo-policy:*`-named
  ruleset whose branch is no longer declared under `enforcement: ruleset` — either removed from
  `policy.yml` entirely, or still present but switched to `enforcement: branch_protection`
  (`apply.prune_rulesets`) — safe, because the name itself is the only ownership marker
  repo-policy needs; no state file exists anywhere.
- **Known limitation:** strict mode cannot fully "unprotect" a `branch_protection`-backed branch
  that's been removed from `policy.yml` — the classic branch protection API has no ownership
  metadata to identify what repo-policy created versus what a human configured by hand. Removing
  branch-protection management for a branch is a manual, GitHub-side action today.
- **Detected but not auto-fixed:** switching a branch's `enforcement:` from `branch_protection` to
  `ruleset` leaves the old classic branch-protection object active on GitHub (same ownership-marker
  problem as the limitation above). `audit`/`plan`/`apply` detect and report this
  (`stale classic branch protection detected`, via `apply.detect_stale_branch_protection`) instead
  of silently reporting the branch compliant, but removing the stale protection is still a manual,
  GitHub-side action. The reverse direction (`ruleset` → `branch_protection`) is fully automatic,
  per the strict-mode bullet above.

## Repo-Level Settings: the `unavailable` Outcome

Two of the seven `repo_settings` fields can come back `unavailable` rather than `ok`/drifted:
`secret_scanning`/`secret_scanning_push_protection` (422 = no GitHub Advanced Security license) and
`private_vulnerability_reporting` (404 or 422 = repo not eligible, e.g. dependency graph disabled).
`unavailable` is informational, not a compliance failure — it never sets `audit`/`plan`'s drift exit
code, and `apply` reports it as a plain message rather than an error. `GitHubClient._request` gained
an `allow_422` parameter (mirroring the existing `allow_404`) specifically to make this
distinguishable from a genuine API error.

## Failure Modes

| Scenario | Impact | Mitigation |
|---|---|---|
| No GitHub token configured | Every API call would 401 | `cli._resolve_token` fails fast with an actionable error before any request is made |
| `secrets.GITHUB_TOKEN` used inside a GitHub Action | Every API call 403s (`Resource not accessible by integration`) | Documented in README/SECURITY as a hard GitHub platform limitation — `GITHUB_TOKEN` has no administration-scope permission under any configuration; a real PAT is required |
| GitHub secondary rate limiting (429) or primary (403 + rate-limit text) | Request would otherwise fail immediately | `github_client._request` retries both with exponential backoff |
| Ruleset list has more entries than one page | `find_ruleset_by_name`/`prune_rulesets` would silently miss entries past page 1 | `list_rulesets` follows the `Link: rel="next"` header until exhausted |
| Malformed `--repo` (no `/`) | Would crash with an unhandled `ValueError` | `cli._split_repo` validates and raises a clean `ClickException` |
| `git` not installed and no `--repo`/`GITHUB_REPOSITORY` given | Would crash with `FileNotFoundError` | Caught and converted to the same clean "could not determine repository" error |

## Technology Stack

| Layer | Technology | Why |
|---|---|---|
| CLI framework | Click | Mature subcommand + exit-code support |
| HTTP client | httpx | Direct control over retries/pagination/headers — avoided PyGithub specifically because its Rulesets coverage lagged the raw API at build time (`docs/adrs/0001-*`) |
| Config validation | Pydantic v2 | Declarative models, strong per-field error messages surfaced by `validate` |
| YAML parsing | PyYAML (`safe_load`) | Standard, minimal |
| Build backend | hatchling | Plain `pyproject.toml`, no Poetry lockfile |
| Release automation | python-semantic-release | Conventional-Commits-driven version bump, changelog, git tag, floating major-version tag, PyPI publish (see `docs/ci-cd.md`) |
| Distribution | Docker container GitHub Action (`python:3.12-slim`) + PyPI package | Two independent consumption paths from one codebase |

## Scaling Model

repo-policy is invoked once per CLI call or once per Action run; there is no persistent process
and no concurrency model. The only per-run cost that grows is the number of GitHub API calls,
which scales with the number of declared branches — `apply.prefetch_rulesets` exists specifically
so that ruleset lookups across many branches cost one `GET /rulesets` call, not one per branch
(see the sequence diagram above).
