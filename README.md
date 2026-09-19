# repo-policy

Lightweight, declarative repository governance for GitHub. Define expected branch protection
and ruleset configuration in YAML; audit, preview, and apply it locally or in CI.

Not a Terraform replacement — no state file, no backend. `repo-policy` is safe to adopt
incrementally on a live repository: by default it only ever touches branches you declare, and
never deletes anything you didn't ask it to manage.

## Install

```bash
pip install repo-policy
```

## Quick start

```yaml
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
```

```bash
repo-policy validate
repo-policy audit --repo acme/widgets
repo-policy plan --repo acme/widgets
repo-policy apply --repo acme/widgets
```

## GitHub Action

```yaml
- uses: shipsolid/repo-policy@v0
  env:
    GITHUB_TOKEN: ${{ secrets.REPO_POLICY_TOKEN }}
  with:
    config: .github/repository-policy.yml
    mode: audit
```

**`secrets.GITHUB_TOKEN` will not work here, in any workflow, no matter what `permissions:` you
grant it** — confirmed against a real repo. GitHub Actions' automatically-generated token has no
permission scope covering branch protection or ruleset administration; that's a platform
constraint, not something a workflow can opt into. Create a PAT with `repo` scope (classic) or
`Administration: Read and write` (fine-grained), store it as a repository secret — `REPO_POLICY_TOKEN`
above is just an example name — and reference that secret instead.

The floating tag tracks the current major version (`v0` until a `1.0.0` release ships), the same
convention `actions/checkout` and similar Actions use.

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
