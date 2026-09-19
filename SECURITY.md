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
