# Roadmap

> Last updated 2026-09-19 · Owner Amit Singh

## Now

| Item                                            | Why it matters                                                                                                        | Status  | Target |
| ----------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ------- | ------ |
| Real-world hardening from live-repo testing     | 3 real bugs found via live verification against a disposable repo (see `docs/test-strategy.md`) were fixed this cycle | shipped | v0.1.4 |
| Document the `GITHUB_TOKEN` platform limitation | Every Action consumer would otherwise hit an unexplained 403 on first use                                             | shipped | v0.1.4 |

## Next

| Item                                                     | Why                                                                                    | Dependency                                | Target |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------- | ----------------------------------------- | ------ |
| Automated end-to-end test against a disposable real repo | Close the gap the manual checklist in `docs/test-strategy.md` currently covers by hand | a scoped CI PAT + disposable-repo fixture | TBD    |
| CODEOWNERS / multi-maintainer ownership                  | Currently single-maintainer; not yet warranted                                         | a second regular contributor              | TBD    |

## Later (directional, unscheduled)

- Org-wide policy inheritance (a default policy an org's repos inherit unless overridden)
- Multi-repository orchestration (`repo-policy apply` across a list of repos in one invocation)
- GitHub App authentication, as an alternative to a PAT (would resolve the `GITHUB_TOKEN` limitation
  more elegantly than "store a PAT as a secret," at the cost of an installable App)
- A way to fully "release" a `branch_protection`-backed branch from repo-policy management in strict
  mode (currently a known, documented limitation — see `ARCHITECTURE.md`)
- Repo-level security & settings management: secret scanning + push protection, Dependabot alerts
  and security-fix automation, private vulnerability reporting, `delete_branch_on_merge`,
  `allow_update_branch`. Out of scope today — repo-policy only manages branch protection/rulesets,
  not repo-wide settings.
- Additional branch-protection fields repo-policy doesn't model yet: `enforce_admins`,
  `dismiss_stale_reviews`, `require_last_push_approval`, `required_conversation_resolution`,
  `lock_branch`, `allow_fork_syncing`. Currently read through from whatever's already set on the
  branch rather than enforced — see `to_api_payload()` / `pull_requests.to_branch_protection()`.

## Explicitly not doing

- **A state file.** The entire safety model (`ARCHITECTURE.md`, `docs/adrs/0003-*`,
  `docs/adrs/0004-*`) is built around not needing one. Any future feature that would require one is
  a sign it belongs in a different tool.
- **A UI or dashboard.** repo-policy is a CLI + Action; a UI is out of scope by design (see README's
  positioning against Terraform / Safe Settings).
- **Other Git providers (GitLab, Bitbucket).** The domain model (branch protection + rulesets) is
  GitHub-specific; supporting another provider would mean a second, differently-shaped backend pair,
  not a small addition.
- **A central server or database.** Zero infrastructure is the differentiator; adding either would
  contradict it.
