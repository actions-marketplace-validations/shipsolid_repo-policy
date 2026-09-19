# repo-policy — Design Spec

- **Date:** 2026-09-19
- **Status:** Approved (design phase) — proceeding to implementation plan
- **Author:** Amit Singh (with Claude)

## 1. Goal

An open-source, lightweight policy-as-code tool for GitHub repository governance. Users declare
expected repository configuration in YAML (`policy.yml`); the tool audits, plans, and applies
that configuration against the GitHub REST API. Runs locally (CLI) or in CI (GitHub Action).

```text
policy.yml
    │
    ▼
 repo-policy
    │
    ├── validate
    ├── audit
    ├── plan
    └── apply
         │
         ▼
   GitHub REST API
         │
         ▼
Branch Protection / Rulesets
```

## 2. Positioning

Not a Terraform replacement. Differentiator: zero infrastructure (no state file, no backend) +
developer-friendly compliance checking and remediation, adopted incrementally per-repo.

```text
              Safe Settings       Terraform        repo-policy
                     │                │                 │
                Org governance      IaC          Developer workflow
                     │                │                 │
                GitHub App       Terraform state    YAML + Action
                                                       │
                                             audit → plan → apply
```

## 3. V1 Scope

**In scope:** GitHub repositories only; YAML configuration; branch protection and GitHub
Rulesets; PR approval requirements; CODEOWNERS review requirement; required status checks;
signed commits; linear history; force-push/deletion controls; `validate`, `audit`, `plan`,
`apply`; `GITHUB_TOKEN` and PAT authentication; CLI + GitHub Action; useful exit codes for CI;
automated tests; semantic releases with a floating `@v1` tag.

**Deferred:** organization-wide governance, GitHub App authentication, multi-repository
orchestration, UI/dashboard, central server, database, other Git providers.

## 4. Architecture

```text
repo-policy/
├── src/repo_policy/
│   ├── cli.py              # Click entry point: validate/audit/plan/apply
│   ├── config.py           # YAML load + Pydantic parse/validate
│   ├── models.py           # PolicyConfig, BranchPolicy, PullRequestPolicy, StatusChecksPolicy
│   ├── github_client.py    # httpx wrapper: auth, retries, get/put branch protection & rulesets
│   ├── audit.py            # orchestrates: load config, fetch current state, run diff
│   ├── diff.py             # desired + current -> list[Change]; shared by audit/plan/apply
│   ├── apply.py            # executes Change list against github_client, honoring scope rules
│   └── policies/
│       ├── branch_protection.py  # translate BranchPolicy <-> classic branch protection payload
│       ├── pull_requests.py      # shared PR-approval field mapping (used by both backends)
│       ├── status_checks.py      # shared required-status-checks field mapping (used by both)
│       └── rulesets.py           # translate BranchPolicy <-> Repository Ruleset payload
├── tests/
├── action.yml               # Docker container action
├── Dockerfile
├── pyproject.toml           # hatchling backend
├── README.md
├── CONTRIBUTING.md
├── SECURITY.md
└── LICENSE
```

Data flow:

```text
Desired State (YAML)
        +
Current State (GitHub API)
        │
        ▼
   Normalized Models
        │
        ▼
      Diff Engine
       /      \
      ▼        ▼
   Compliant   Changes
                 │
                 ▼
              Apply
```

`pull_requests.py` and `status_checks.py` are shared translators consumed by both
`branch_protection.py` and `rulesets.py` — the PR-approval and status-check concepts are
identical across both backends; only the outer payload shape differs.

## 5. Config Schema

```yaml
version: 1
strict: false                        # optional global default — inherited by branches that omit their own `strict`

branches:
  main:
    enforcement: branch_protection   # or "ruleset" — default: branch_protection
    strict: false                    # opt-in full field-level enforcement — default: false

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

Models (Pydantic v2, in `models.py`):

- `PolicyConfig{version: int, strict: bool = False, branches: dict[str, BranchPolicy]}`
- `BranchPolicy{enforcement: Literal["branch_protection","ruleset"] = "branch_protection", strict: bool = False, pull_requests: PullRequestPolicy | None, status_checks: StatusChecksPolicy | None, signed_commits: bool | None, linear_history: bool | None, allow_force_push: bool | None, allow_deletion: bool | None}`
- `PullRequestPolicy{required: bool, approvals: int, code_owner_review: bool}`
- `StatusChecksPolicy{required: list[str]}`

`validate` parses YAML into `PolicyConfig`; Pydantic validation errors are reported with
file/field context and exit code 2.

## 6. Normalized State & Diff Engine

`github_client.py` fetches current branch protection or ruleset state per branch and normalizes
it into the same shape as `BranchPolicy`, so `diff.py` compares two instances of one model
regardless of backend.

`diff.py` exposes a single function: `diff(desired: BranchPolicy, current: BranchPolicy) ->
list[Change]`, where `Change{field, current_value, desired_value, action}`. This is the one
source of truth consumed by `audit` (compliance check), `plan` (human-readable preview), and
`apply` (execution) — there is no separate diff logic per command.

## 7. Apply Semantics (idempotency-critical)

**Managed-scope (default, no config needed):**

- `apply` never touches a branch that isn't a key under `branches:` in `policy.yml`.
- Within a declared branch, only the fields present in `policy.yml` are enforced. For the
  `branch_protection` backend this means a read-merge-write: fetch the full current protection
  payload, overlay only the modeled+declared fields, PUT the merged result — GitHub settings
  outside repo-policy's schema (and modeled-but-undeclared fields) are preserved untouched.
- For the `ruleset` backend, repo-policy only ever creates/reads/updates a ruleset named
  `repo-policy:<branch>`. It never inspects or modifies any other ruleset in the repository. The
  naming convention is the ownership marker — no state file is needed.

**Strict mode (`strict: true`), opt-in:** set at the top level of `policy.yml` as a default for
every branch, or per-branch to override that default. A branch's own `strict` value always wins
when both are set.

- Within a declared branch, fields left unset in `policy.yml` are now actively reset to the
  schema default (e.g. `linear_history` unset means "must be off"), instead of being left alone.
  This is full field-level drift correction, but still scoped to branches you've declared.
- For the `ruleset` backend only, strict additionally deletes any `repo-policy:*`-named ruleset
  whose branch key no longer appears in `policy.yml` — safe because the name itself proves
  repo-policy created it.
- `branch_protection` has no equivalent safe deletion path (the classic API has no ownership
  metadata), so strict mode never removes branch protection outright, even for branches dropped
  from the config. This is a known, intentional v1 limitation — call it out in the README.

Net effect: adopting repo-policy on a live repository is non-destructive by default. `strict` is
explicit, per-branch, reversible by editing YAML, and requires no state file anywhere.

## 8. CLI

Entry point: `repo-policy` (Click), commands `validate`, `audit`, `plan`, `apply`.

| Command  | Behavior                                                        | Exit codes                                  |
| -------- | ---------------------------------------------------------------- | -------------------------------------------- |
| validate | Parse + validate `policy.yml`                                    | 0 ok, 2 invalid config                       |
| audit    | Read-only compliance check via the diff engine; built for CI gating | 0 compliant, 1 drift found, 3 API/auth error |
| plan     | Same diff engine, renders the human-readable +/-/~/✓ preview      | 0 compliant, 1 drift found, 3 API/auth error |
| apply    | Executes the changes `plan` would show, honoring scope rules      | 0 success (incl. no-op), 3 API/auth error    |

Repo targeting: `--repo owner/name`, else auto-detected from the local git `origin` remote, else
`$GITHUB_REPOSITORY` (always set inside GitHub Actions).

Auth: `--token`, else `GITHUB_TOKEN`, else `GH_TOKEN`.

## 9. GitHub Action

`action.yml` as a Docker container action (`Dockerfile`), consumed as:

```yaml
- uses: shipsolid/repo-policy@v1
  with:
    config: .github/repository-policy.yml
    mode: audit
```

## 10. Packaging & Release

- `pyproject.toml` with `hatchling` build backend — plain pip-installable, no Poetry lockfile.
- Runtime deps: `httpx`, `pyyaml`, `pydantic>=2`, `click`.
- Dev deps: `pytest`, `respx` (httpx-native request mocking), `ruff`, `mypy`.
- Python 3.10+.
- Release automation: `python-semantic-release` driven by Conventional Commits (version bump +
  CHANGELOG.md + git tag), plus a workflow step that moves the floating `v1` tag to each new
  release tag, matching the convention consumers of `uses: shipsolid/repo-policy@v1` expect.

## 11. Testing Strategy

- Unit tests per module under `tests/`, mirroring `src/repo_policy/`.
- GitHub API interactions mocked with `respx` against recorded fixture payloads — no live API
  calls in the test suite.
- One named idempotency test (directly validates the spec's core requirement): run `apply` twice
  against a mocked "already compliant" repository and assert the second run issues zero mutating
  HTTP calls.

## 12. Key Decisions (resolved during brainstorming)

| Decision                | Choice                                                              |
| ------------------------ | -------------------------------------------------------------------- |
| GitHub API client        | Direct HTTP via `httpx` (not PyGithub) — full control, no lag on Rulesets endpoint coverage |
| Backend selection         | Explicit `enforcement:` field per branch, default `branch_protection` |
| Config validation         | Pydantic v2                                                          |
| Apply scope (safety)      | Managed-scope by default; opt-in `strict: true` for full enforcement |

## 13. Known Limitations (v1)

- `strict` mode cannot delete/reset classic branch protection for a branch removed from
  `policy.yml` — no ownership marker exists in that API. Migrating a branch off repo-policy
  management for `branch_protection` requires a manual GitHub-side change.
- Rulesets targeting is 1:1 with a branch key (`repo-policy:<branch>`) in v1 — no support for
  multi-branch ruleset patterns or repo-wide rulesets.
- No organization-level policy inheritance; each repository's `policy.yml` is fully self-contained.
