---
adr: 0003
title: Default to managed-scope (non-destructive) apply; make full enforcement an opt-in
status: accepted
date: 2026-09-19
deciders: Amit Singh
domain: platform
---

## Context

A policy tool that reconciles live infrastructure has to answer: what happens to a setting nobody
declared in the config? Terraform's answer is "reset to default, or delete" — full desired-state
enforcement. For a tool explicitly positioned as adoptable *incrementally* on an already-live
repository (see README, "Not a Terraform replacement"), that default is actively dangerous: the
first `apply` on an existing repo could reset or delete settings a team configured by hand years
ago, with no state file to warn anyone what's about to change.

## Decision

Default behavior ("managed-scope") never touches a branch absent from `policy.yml`, and within a
declared branch only ever sets the fields explicitly present — everything else is read from
current state and passed through unchanged. Full desired-state enforcement is an explicit opt-in
(`strict: true`, top-level default or per-branch override).

## Alternatives Considered

- **Always full enforcement (Terraform-style)** — rejected as the default specifically because it
  contradicts the "safe to adopt on a live repo" positioning; an accidental first `apply` should
  never be a surprise.
- **Always managed-scope, no strict option at all** — simpler, smaller surface area, but removes a
  legitimate need: some teams do want full drift correction. Rejected as too limiting long-term.

## Consequences

- `BranchPolicy`'s six policy fields had to be modeled as `Optional[...] = None` specifically so
  "not declared" is representable and distinguishable from "declared as false/empty" — this is the
  single modeling decision everything else in `diff.py`/`apply.py` is built around
  (`diff.resolve_desired`).
- Every "empty" schema default (e.g. `status_checks`'s absence) has to be represented *identically*
  to what the live-API translators produce for "nothing configured," or strict mode reports
  phantom drift forever — this exact bug shipped once and was only caught by testing against a
  real repository (see `docs/test-strategy.md`).
- `strict` mode's ruleset-pruning behavior (`0004-ruleset-ownership-via-naming-convention.md`) only
  works because ruleset ownership has a naming-convention marker; branch protection has no
  equivalent, so strict mode can tighten fields within a declared branch but can never fully
  "unprotect" a branch removed from the config — a known, documented v1 limitation
  (`ARCHITECTURE.md`).

## Links

- `src/repo_policy/diff.py` (`resolve_desired`, `_SCHEMA_DEFAULTS`)
- `docs/test-strategy.md` (the phantom-drift regression)
