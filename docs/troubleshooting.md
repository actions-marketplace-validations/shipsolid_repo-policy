# Troubleshooting

## `Error: no GitHub token found; pass --token or set GITHUB_TOKEN/GH_TOKEN`

No token was found in `--token`, `GITHUB_TOKEN`, or `GH_TOKEN`. Set one of those. See
[SECURITY.md](../SECURITY.md) for the required token permissions.

## `GitHub API error 403 ... Resource not accessible by integration` (inside a GitHub Action)

You're using the automatically-generated `secrets.GITHUB_TOKEN`. This will never work, regardless
of the `permissions:` block on your workflow — `GITHUB_TOKEN` has no permission scope covering
repository administration. Create a PAT (classic `repo` scope, or fine-grained
`Administration: Read and write`), store it as a repository secret, and reference that secret
instead. See the README's GitHub Action example.

## `GitHub API error 401 ... Bad credentials`

The token is present but invalid or expired. Regenerate it.

## `invalid repository 'xyz'; expected 'owner/name'`

`--repo` (or a resolved `GITHUB_REPOSITORY`) didn't contain a `/`. Pass the full `owner/name` form.

## `could not determine repository; pass --repo owner/name`

None of `--repo`, `$GITHUB_REPOSITORY`, or a `git remote get-url origin` in the current directory
resolved to a repository. This also fires if `git` isn't installed and no `--repo`/
`$GITHUB_REPOSITORY` was supplied.

## `policy file not found: <path>` / `policy file is empty: <path>`

Check `--config`'s path is correct relative to your current working directory (CLI) or the
Action's `config:` input is relative to the repo root (Action).

## `invalid policy config in <path>: ...`

`validate`'s or `audit`'s Pydantic error output — each line names the exact field and what's wrong
with it (e.g. `branches.main.enforcement: unsupported value`).

## `apply` reports a change every single run, even though nothing should be different

This was the strict-mode phantom-drift bug (fixed — see `docs/test-strategy.md`) on versions
before it shipped. Upgrade. If it recurs on a current version, it's a new bug: file an issue with
the exact `plan` output and your `policy.yml`.

## A ruleset got deleted that I didn't expect

`strict: true` prunes any `repo-policy:*`-named ruleset whose branch is no longer declared in
`policy.yml` (see `../ARCHITECTURE.md`'s Apply Safety Model). Check whether the branch was
recently removed from the config, and whether `strict` is set at the top level (it applies as a
default to every branch unless overridden). This never touches a ruleset that isn't named
`repo-policy:*`.

## Docker image fails to build with `Readme file does not exist: README.md`

If you're building the `Dockerfile` yourself: it must be built with the repo root as build
context, and `README.md` must be copied in alongside `pyproject.toml` — hatchling's build
validates the `readme` field declared in `pyproject.toml` at install time.
