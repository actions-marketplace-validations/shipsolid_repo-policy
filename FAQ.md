# FAQ

## Why doesn't `secrets.GITHUB_TOKEN` work inside my Action workflow?

It can't, for any workflow, no matter what `permissions:` you grant it. GitHub's auto-generated
token has no permission scope that covers branch protection or ruleset administration — this was
confirmed against a real workflow run, not assumed. You need a real PAT stored as a repository
secret. See the README's GitHub Action example and `docs/troubleshooting.md`.

## Why is the floating tag `@v0` and not `@v1`?

Floating major-version tags (the convention `actions/checkout@v4` etc. use) track the *actual*
current major version of the package. repo-policy hasn't shipped a `1.0.0` release yet, so the
correct floating tag is `v0`. It will become `v1` automatically the first time a `1.0.0` release
ships.

## Why no state file, if Terraform has one?

Because the entire point of repo-policy is to be safe to adopt on a live repository without first
importing its current state into anything. See `ARCHITECTURE.md`'s Apply Safety Model and
`docs/adrs/0003-*`/`docs/adrs/0004-*` for exactly how ownership is tracked without one (a naming
convention for rulesets; an "only touch declared branches/fields" rule for classic branch
protection).

## Will `apply` ever delete something I didn't ask it to?

Only in one specific case: `strict: true` deletes a `repo-policy:<branch>`-named ruleset if that
branch is removed from `policy.yml`. It will never touch a ruleset not matching that exact naming
pattern, and it will never delete or reset classic branch protection for a branch removed from the
config (a known limitation, not a safety gap — see `ARCHITECTURE.md`).

## Can I manage the same branch with both branch protection and a ruleset?

Not through repo-policy's config — `enforcement` is one value per branch. GitHub itself allows
both to exist simultaneously on the same branch; repo-policy just won't manage both at once for
you.

## Does repo-policy work on GitHub Enterprise Server?

Untested. `github_client.GitHubClient` accepts a `base_url` parameter, so pointing it at a GHES
instance's API URL is architecturally possible, but the CLI doesn't currently expose a flag for it
and it has never been verified against a real GHES instance. Treat as unsupported until someone
tries it and reports back.

## Why Pydantic instead of stdlib dataclasses for the config model?

Declarative models and strong, field-level error messages on `validate` — a bad `policy.yml`
should tell you exactly which field is wrong, not just that the file failed to parse.
