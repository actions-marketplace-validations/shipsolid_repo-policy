# Test Strategy

## Test Pyramid

121 tests, all unit-level, organized one file per source module (`tests/test_<module>.py`) plus
`tests/test_idempotency.py` (one integration-shaped test) and `tests/test_policies_parity.py` (a
cross-backend regression guard). No end-to-end tests run in CI — the true end-to-end verification
for this project is manual, against a real repository, documented below.

## Approach: TDD throughout

Every module in `src/repo_policy/` was built test-first: write the failing test, watch it fail for
the expected reason, implement the minimal code to pass, run the full suite, commit. This is
enforced by convention, not tooling — there's no coverage gate in CI today (see Known Gaps).

## What the mocked suite is good at

- Every GitHub API interaction is mocked via `respx` against real-shaped fixture payloads (built
  from GitHub's actual documented request/response schemas, not guesses) — see
  `tests/test_github_client.py` for retry/pagination/auth coverage.
- The diff/resolve engine (`tests/test_diff.py`) and both backend translators
  (`tests/test_policies_branch_protection.py`, `tests/test_policies_rulesets.py`) are exercised
  field-by-field, including the polarity inversion of `allow_force_push`/`allow_deletion` relative
  to every other field.
- `tests/test_idempotency.py` proves, at the unit level, that applying an already-compliant policy
  twice makes zero mutating calls the second time — the tool's core correctness promise.
- `tests/test_policies_parity.py` is a parametrized guard: for every field in `diff._FIELDS`, both
  the `branch_protection` and `ruleset` backends must respond to it. This exists specifically
  because a bug once shipped with zero test coverage in exactly the gap this test now closes.

## What mocking alone could not catch — four real bugs, found only by testing against a live repo

Mocked tests describe the API the way the author believes it behaves. All four of these bugs
passed a 100%-green mocked suite before being found:

1. **Silent field clobbering.** `apply` rebuilt the entire `required_pull_request_reviews` /
   `required_status_checks` payload on any change, hardcoding three unmodeled GitHub fields
   (`dismiss_stale_reviews`, `require_last_push_approval`, status-check `strict`) to `False` —
   silently resetting them if a human had set them manually. Found during code review, confirmed
   with a live-repo reproduction before fixing.
2. **Strict-mode phantom drift.** `diff._SCHEMA_DEFAULTS["status_checks"]` was
   `StatusChecksPolicy(required=[])`, but the real API translators represent "no status checks
   configured" as `None` — semantically identical, not `==`-equal. Every `strict: true` apply
   against an already-compliant, unconfigured branch reported permanent 1-field drift and issued
   an unnecessary API call, forever. **Only surfaced by running `repo-policy apply` with
   `strict: true` against a real repository** and noticing the tool claimed 1 change when nothing
   should have changed. No mocked test combined "strict mode" with "current state has
   `status_checks=None`" — the exact combination that broke.
3. **`__version__`/PyPI version divergence.** `python-semantic-release`'s `version_toml` config
   only updates `pyproject.toml`; the hardcoded string in `src/repo_policy/__init__.py` silently
   drifted across 4 releases. Found by literally running `pip install repo-policy` in a clean venv
   and checking `repo_policy.__version__` against `pip show`'s reported version.
4. **`allow_fork_syncing`'s wrong permissive default.** `diff._SCHEMA_DEFAULTS["allow_fork_syncing"]`
   was `True`, chosen to match the sibling `repo_security` tool's own recommended baseline value —
   never independently verified against live GitHub. **Only surfaced by running `repo-policy apply`
   against a real repository** and independently checking the resulting branch protection via
   `gh api`: GitHub silently discards `allow_fork_syncing: true` on any branch where `lock_branch`
   is `false`, resetting it to `false` regardless of what's sent. Because `True` was also the value
   `from_api(None, ...)` used to represent "nothing configured," `diff.resolve_desired()`'s
   managed-scope current-state inheritance carried the broken pairing into *any* first-time `apply`
   against a previously-unprotected branch — even for a `policy.yml` that never mentions
   `allow_fork_syncing` at all. No mocked test could catch this: it requires a real GitHub API
   response to observe that a value sent in a `PUT` doesn't persist. Fixed by flipping the default
   to `False` (the value GitHub always honors regardless of `lock_branch`) and adding a model
   validator that rejects an explicit `allow_fork_syncing: true` declaration unless `lock_branch:
   true` is also declared — see
   `docs/superpowers/plans/2026-09-19-fix-allow-fork-syncing-polarity.md`.

The pattern across all four: the bug was invisible to any test that only asserted repo-policy's
own internal consistency. Each one required checking repo-policy's output against an independent,
real source of truth — a live repo's actual API state, or a real PyPI install.

## Manual Verification Checklist (run before any release you don't fully trust)

Against a disposable repository:

1. `validate` a config, confirm exit 0 on valid / exit 2 on invalid.
2. `plan` against an unprotected branch — confirm it reports every field as a change.
3. `apply`, then independently confirm via
   `gh api repos/<owner>/<repo>/branches/<branch>/protection` that the real state matches.
4. `plan` again — confirm zero drift (real-world idempotency, not just the mocked test).
5. Repeat 2-4 with `enforcement: ruleset` on a second branch, cross-checking
   `gh api repos/<owner>/<repo>/rulesets`.
6. Remove a declared branch from the config with `strict: true`, `apply`, confirm the orphaned
   ruleset (and only that one) is deleted.
7. Restore the repository to its original state.

## Known Gaps

- No CI-enforced coverage threshold.
- No automated end-to-end test against a real GitHub repository — the checklist above is manual.
  Automating it would require a disposable-repo-per-run fixture and a real, least-privilege PAT in
  CI secrets; deferred (see `ROADMAP.md`).
- No test exercises GitHub's classic-branch-protection-specific edge cases beyond what's modeled
  (e.g. `restrictions` with actual user/team push restrictions configured).
