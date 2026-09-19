---
adr: 0004
title: Identify repo-policy-owned rulesets by name, not a state file
status: accepted
date: 2026-09-19
deciders: Amit Singh
domain: platform
---

## Context

`strict` mode needs to know which rulesets repo-policy is responsible for, so it can safely delete
ones whose branch was removed from `policy.yml` — without ever touching a ruleset some other tool
or human created. Terraform-style tools solve "what do I own" with a state file. repo-policy is
explicitly positioned as needing none (see README, and `0003-managed-scope-default-strict-opt-in.md`'s
context).

## Decision

Every ruleset repo-policy manages is named exactly `repo-policy:<branch>`. Ownership is proven
entirely by that name: `apply` only ever creates, reads, or updates a ruleset with that exact name
for a declared branch, and `prune_rulesets` (strict mode only) only ever deletes rulesets matching
the `repo-policy:` prefix.

## Alternatives Considered

- **A local or remote state file** (Terraform-style) — rejected outright; a state file that can
  drift from reality is exactly the class of bug repo-policy's positioning exists to avoid, and it
  reintroduces the "zero infrastructure" cost the tool is meant to avoid.
- **A ruleset metadata/tag field** — GitHub's Rulesets API doesn't currently expose an
  arbitrary-metadata field suitable for this; the name is the only sufficiently unique, always-
  fetched identifier available.

## Consequences

- No state file, anywhere, ever — matches the tool's core positioning.
- The naming convention is a hard constraint: nothing else in the org should ever create a ruleset
  named `repo-policy:<branch>` on a repo-policy-managed repository, or it will be treated as
  repo-policy's own and become eligible for modification/deletion in strict mode.
- This mechanism is ruleset-specific. Classic branch protection has no equivalent naming/tagging
  capability, which is precisely why strict mode's deletion behavior is ruleset-only
  (`0003-managed-scope-default-strict-opt-in.md`).
- v1 maps exactly one ruleset to one branch; a repo needing one ruleset to cover multiple branch
  patterns is out of scope (`ROADMAP.md`).

## Links

- `src/repo_policy/policies/rulesets.py` (`ruleset_name`)
- `src/repo_policy/apply.py` (`prune_rulesets`)
