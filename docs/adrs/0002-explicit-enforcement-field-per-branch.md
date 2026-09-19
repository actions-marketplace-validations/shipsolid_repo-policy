---
adr: 0002
title: Select branch protection vs. ruleset backend with an explicit per-branch field
status: accepted
date: 2026-09-19
deciders: Amit Singh
domain: platform
---

## Context

A branch can be governed by GitHub's classic branch protection API or by a repository ruleset —
two different, non-overlapping APIs with different capabilities. repo-policy's directory layout
already separates `policies/branch_protection.py` and `policies/rulesets.py`; something has to
decide which one governs a given branch.

## Decision

Add an explicit `enforcement: branch_protection | ruleset` field to `BranchPolicy`, defaulting to
`branch_protection`, set per branch in `policy.yml`.

## Alternatives Considered

- **Auto-detect from current repo state** — inspect whether a branch currently has classic
  protection or a ruleset, and manage whichever is found. Rejected: makes "which backend am I
  governing" implicit, harder to reason about in a `plan` diff, and ambiguous on first-ever
  creation (which one should `apply` create?).
- **Classic branch protection only for v1** — drop ruleset support entirely. Rejected: contradicts
  the explicit v1 scope of supporting both, and GitHub's own direction is toward rulesets.

## Consequences

- Deterministic: reading `policy.yml` alone tells you which API a branch will be managed through,
  with no live-state lookup required.
- The two backends can diverge in behavior without ambiguity — see `0004-ruleset-ownership-via-naming-convention.md`
  for how ruleset ownership and deletion differ from branch protection's.
- A team migrating a branch from one backend to the other does so by editing one field, at the
  cost that repo-policy does not automatically clean up the *other* backend's leftover state (out
  of scope for v1 — see `ROADMAP.md`).

## Links

- `src/repo_policy/models.py` (`BranchPolicy.enforcement`)
- `ROADMAP.md`
