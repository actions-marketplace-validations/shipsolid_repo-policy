# CHANGELOG


## v0.3.0 (2026-09-19)

### Documentation

- Document the repo_settings section and its unavailable outcome
  ([`d7095a4`](https://github.com/shipsolid/repo-policy/commit/d7095a4358c2e6542fc7a90a84c78b39be46364b))

ARCHITECTURE.md's Domain Model, Container/Component View, and a new Repo-Level Settings subsection;
  ROADMAP.md's Later section updated to mark this phase shipped.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

### Features

- Add repo_settings section — delete_branch_on_merge, allow_update_branch
  ([`e3857e7`](https://github.com/shipsolid/repo-policy/commit/e3857e72ca8a80be032f07221d7506f0722552bb))

First slice of repo-wide (non-branch) settings management, closing part of the gap against a sibling
  tool's fixed baseline. Establishes the full new architecture end-to-end: RepoSettingsPolicy
  schema, pure diff translation (policies/repo_settings.py), orchestration (repo_settings.py),
  rendering, and CLI wiring in audit/plan/apply. diff_security_and_analysis/diff_toggle ship as
  pure, fully-tested functions here but aren't wired into orchestration yet -- that happens in the
  task that also adds the matching live GitHubClient method, so no commit in this series ever
  reports a policy.yml field as drifted that apply can't actually fix. Zero API calls when
  policy.yml has no repo_settings section, matching every existing adopter's current behavior
  exactly.

Includes the Phase 2 implementation plan (written earlier in the conversation, corrected here after
  a real mypy failure surfaced the premature security_and_analysis wiring this commit's message
  describes avoiding).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Enforce automated_security_fixes (Dependabot security updates)
  ([`649f107`](https://github.com/shipsolid/repo-policy/commit/649f107540c2426bed7a9d2294356584c1996660))

Must apply after vulnerability_alerts in the same run -- GitHub rejects enabling Dependabot security
  updates before Dependabot alerts. Guarded two ways: RepoSettingsPolicy's model validator (Task 1)
  rejects a policy.yml that declares automated_security_fixes: true without also declaring
  vulnerability_alerts: true, at parse time; apply_repo_settings additionally sequences the two live
  API calls correctly for the case where both are changing in the same run.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Enforce private_vulnerability_reporting
  ([`e55403b`](https://github.com/shipsolid/repo-policy/commit/e55403bcc6bfe3117290d6659936bf2bd8c00337))

Free on every repo, but not every repo is eligible (e.g. dependency graph disabled) -- introduces
  the unavailable outcome, informational and distinct from drift or an error, first used here.
  GitHubClient._request gains allow_422 (mirroring the existing allow_404) to make this
  distinguishable from a genuine API error.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Enforce secret_scanning and secret_scanning_push_protection
  ([`d979394`](https://github.com/shipsolid/repo-policy/commit/d97939476b0f091bc232e25ae5f485c0a24cd8b2))

Highest security value in this series, GHAS-gated -- 422 means no GitHub Advanced Security license,
  surfaced as unavailable (Task 4's pattern), not an error. Wires diff_security_and_analysis/
  to_security_and_analysis_payload (pure functions shipped in Task 1) into
  plan_repo_settings/apply_repo_settings for the first time, now that
  GitHubClient.update_security_and_analysis exists to make them usable end-to-end. Completes the
  7-field repo_settings series.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Enforce vulnerability_alerts (Dependabot alerts)
  ([`d46c538`](https://github.com/shipsolid/repo-policy/commit/d46c538fddf180744ed74e2484518b5c465bb261))

Free on every repo. Foundational for the next field in this series (automated_security_fixes), which
  GitHub requires this to already be enabled before it can be turned on.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


## v0.2.0 (2026-09-19)

### Bug Fixes

- Drop redundant forward-reference quotes on BranchPolicy validator
  ([`6f64b39`](https://github.com/shipsolid/repo-policy/commit/6f64b39cf69b7b96b87ecc9df80f731ddd905b6f))

ruff (UP037) flagged the return type annotation on _reject_ruleset_unsupported_fields -- unnecessary
  since models.py already has `from __future__ import annotations`. Caught running this project's
  actual CI checks (ruff + mypy), not just pytest.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

### Chores

- Gitignore .claude/ (worktree tool state)
  ([`1291c30`](https://github.com/shipsolid/repo-policy/commit/1291c30f17acb376f1874f16fef690f6269c3326))

EnterWorktree creates worktrees under .claude/worktrees/ but nothing ignored the directory -- a
  future 'git add -A' could have swept an entire linked worktree (including its own .venv and nested
  .git) into a commit. No tracked content exists under .claude/ today.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

### Documentation

- Add branch-protection field-parity plan; reformat ROADMAP tables
  ([`53085b6`](https://github.com/shipsolid/repo-policy/commit/53085b6e66c7c186e2afd188a04c488d6edac97f))

Plan closes the two "Later" gap-analysis bullets added earlier against the sibling repo_security
  baseline tool. ROADMAP.md's table reformat is an editor auto-format pass with no content change.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Correct stale PyPI trusted-publishing failure narrative
  ([`537485f`](https://github.com/shipsolid/repo-policy/commit/537485fdf81b1773c9a7cc45a73d01c953a330e9))

Both the release.yml comment and docs/ci-cd.md read as if PyPI publish was still failing. It isn't:
  v0.1.0-v0.1.2 failed with invalid-publisher because the trusted publisher wasn't yet registered on
  pypi.org, but v0.1.3 and v0.1.4 published successfully once it was. Confirmed against the actual
  Actions run logs and live PyPI project state.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Reflect the 6 newly-modeled branch-protection fields
  ([`ac6d515`](https://github.com/shipsolid/repo-policy/commit/ac6d515569d164c84ef9a0503d57e5cc037469cb))

ARCHITECTURE.md's Domain Model and Apply Safety Model sections, and ROADMAP.md's Later section,
  described the pre-this-plan state (fields read-through/unmodeled). Updates both to match what
  Tasks 1-5 shipped.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

### Features

- Model allow_fork_syncing, branch_protection-only
  ([`4cc46b4`](https://github.com/shipsolid/repo-policy/commit/4cc46b4449b150ecee1be718542db4644256a789))

Completes the four branch_protection-only fields (with enforce_admins,
  required_conversation_resolution, lock_branch). Inverted polarity like
  allow_force_push/allow_deletion: GitHub's own default is true (syncing allowed), so true/unset is
  the permissive value here, not false.

Also fixes tests/test_policies_parity.py's own PERMISSIVE fixture, which never got the three earlier
  fields either -- masked until now because model_copy(update=...) always sets a real value on the
  'resolved' side, so an unset PERMISSIVE's implicit bool(None)==False happened to match each
  earlier field's real permissive default. allow_fork_syncing's inverted polarity broke that
  coincidence and the parity guard caught it, exactly as designed. Plan doc updated to match.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Model dismiss_stale_reviews and require_last_push_approval
  ([`41e59cb`](https://github.com/shipsolid/repo-policy/commit/41e59cb84d08c9e6ebb7a858bb82049ccda5a254))

Previously read through from live GitHub state and never enforced. Both GitHub backends (classic
  branch protection's required_pull_request_reviews, and the ruleset pull_request rule's parameters)
  already had a slot for these -- converts them from unmodeled/preserved to declared/enforced,
  following the same pattern approvals and code_owner_review already use.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Model enforce_admins, branch_protection-only
  ([`97a531a`](https://github.com/shipsolid/repo-policy/commit/97a531a80869d3d686b64464ba6e0c350e2999bc))

Highest-impact of the branch-protection fields the v1 schema doesn't model: without it, a repo admin
  can bypass every other declared rule at will. No GitHub Rulesets equivalent exists (would require
  bypass_actors role-ID configuration, out of scope here), so this is branch_protection enforcement
  only -- a new BranchPolicy model validator rejects declaring a non-permissive value under
  enforcement: ruleset at policy.yml parse time (the permissive value itself is still allowed
  through, since rulesets.from_api's internal "current state" representation must be able to
  construct it too), and rulesets.from_api hardcodes the field to its permissive constant so no
  ruleset-enforced branch ever shows phantom drift for a field it structurally cannot represent.

Also fixes tests/test_diff.py's PERMISSIVE fixture, which didn't set enforce_admins explicitly and
  defaulted to None -- diverging from every real from_api() call, which now always returns a
  concrete False. Left unfixed this reproduces the exact strict-mode phantom-drift bug class
  docs/test-strategy.md documents from earlier live-repo testing. Plan doc updated in the same
  commit to match: the validator's actual shape (a permissive-value-aware dict, not a plain non-None
  check) and the added test_diff.py step were both discovered only while running the real test
  suite, not anticipated when the plan was written.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Model lock_branch, branch_protection-only
  ([`4ff8c9e`](https://github.com/shipsolid/repo-policy/commit/4ff8c9eaa81d5007bf66d548c7233f8631f50086))

Makes the branch fully read-only when true. No ruleset rule type exists for this at all --
  branch_protection-only, guarded by the same ruleset-unsupported-fields validator as enforce_admins
  and required_conversation_resolution.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Model required_conversation_resolution, branch_protection-only
  ([`5b34a5c`](https://github.com/shipsolid/repo-policy/commit/5b34a5c00cca09e5aae3e33159e393fbe52faa4c))

Same shape as enforce_admins: GitHub's nearest ruleset equivalent
  (required_review_thread_resolution) only exists as a pull_request rule parameter, which doesn't
  always exist (pull_requests.required can be false) -- rather than build a mapping that's sometimes
  silently unenforceable, this stays branch_protection-only, guarded by the same model validator
  enforce_admins added.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


## v0.1.5 (2026-09-19)

### Chores

- Remove internal planning docs (spec + implementation plan)
  ([`cc06ebf`](https://github.com/shipsolid/repo-policy/commit/cc06ebfa8cbf79003ca70a9c0a853d2be56de130))

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

### Documentation

- Document that GITHUB_TOKEN cannot manage branch protection/rulesets
  ([`12a725c`](https://github.com/shipsolid/repo-policy/commit/12a725c08bf51141151cd1229126b9cc6edbfaa6))

Confirmed against a real GitHub Actions run: the auto-generated secrets.GITHUB_TOKEN has no
  permission scope covering repository administration, under any permissions: configuration -- it
  always fails with 403 Resource not accessible by integration on branch protection/ruleset
  endpoints. This is a GitHub platform constraint, not something repo-policy or a workflow can work
  around. Consumers must supply a real PAT via a custom repository secret; the README's GitHub
  Action example and SECURITY.md now say so explicitly.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Write full documentation set for repo-policy
  ([`a81512f`](https://github.com/shipsolid/repo-policy/commit/a81512fee5ab5c44ccb9bfba003dbef885b1726a))

Adds ARCHITECTURE.md, 4 ADRs, docs/ci-cd.md, docs/test-strategy.md, docs/troubleshooting.md,
  ROADMAP.md, FAQ.md, SUPPORT.md, and CODE_OF_CONDUCT.md; updates README/CONTRIBUTING/SECURITY in
  place (fixes a dead link to the deleted planning spec, adds a CLI reference table, adds a threat
  model). Content is grounded in this project's actual build history -- the three bugs live testing
  caught, the GITHUB_TOKEN platform limitation, and the release-pipeline step-ordering fix -- rather
  than generic template filler. Documentation domains that don't apply to a CLI tool (SLO, runbook,
  PRD, k8s ops, etc.) were deliberately skipped, not padded in.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


## v0.1.4 (2026-09-19)

### Bug Fixes

- Keep repo_policy.__version__ in sync with the published version
  ([`afe820a`](https://github.com/shipsolid/repo-policy/commit/afe820a045d323a28b2df0b76a2e131768818b3d))

Confirmed via a real 'pip install repo-policy' from PyPI: __version__ still reported 0.1.0 while the
  actual published package was 0.1.3. semantic-release's version_toml only updates pyproject.toml,
  never the hardcoded string in __init__.py -- added version_variables so both stay in sync on every
  future release, corrected the current value, and changed the test to check the value is a valid
  semver string instead of hardcoding a literal that will always drift again otherwise.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


## v0.1.3 (2026-09-19)

### Bug Fixes

- Pin dependency upper bounds to prevent future breaking installs
  ([`c259eba`](https://github.com/shipsolid/repo-policy/commit/c259eba3180c45e10b6b6dca44b2ab56b7aaaf09))

Runtime dependencies had no upper bound (httpx>=0.27, pyyaml>=6.0, pydantic>=2.0, click>=8.1), so a
  future major-version release of any of them could silently break installs with no warning. Caps
  each at its current major version; dev-only deps are left open since they don't affect what ships
  to consumers.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

### Continuous Integration

- Run the floating major tag step before the PyPI publish step
  ([`9e11f36`](https://github.com/shipsolid/repo-policy/commit/9e11f3688a35d9ef1177cab92b9227d465f284bd))

Sequenced after PyPI meant a PyPI failure (which has occurred on every release so far, since trusted
  publishing was never configured) silently skipped the tag move every time -- confirmed via the
  last 3 release runs, where 'Move floating major tag' shows as skipped and no v1 tag was ever
  created. These two steps are independent; the Action's own consumers (uses:
  shipsolid/repo-policy@v1) must not be blocked by an unrelated PyPI outage.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

### Documentation

- Correct the Action's floating tag from @v1 to @v0
  ([`a58436c`](https://github.com/shipsolid/repo-policy/commit/a58436ca0f976b380c42a979378fa7c064a12e50))

The release workflow's tag-move step correctly extracts the CURRENT major version from each semver
  release tag (v0.1.3 -> major 0) -- that step was working correctly the whole time. The bug was
  mine: I manually created a v1 tag earlier, based on the README's example usage rather than actual
  semver, and it silently went stale since the workflow only ever updates v0 (we haven't shipped
  1.0.0). Deleted the stale v1 tag and corrected the README to the tag that's actually kept up to
  date.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


## v0.1.2 (2026-09-19)

### Bug Fixes

- Strict mode reported phantom drift for unconfigured status checks
  ([`90b2576`](https://github.com/shipsolid/repo-policy/commit/90b25761d978aeab0bc71a5e81361f7e84399f02))

Found via live verification against a real repo (shipsolid/playground), not the earlier mocked
  audit. diff.py's strict-mode schema default for status_checks was StatusChecksPolicy(required=[]),
  but branch_protection .from_api() and rulesets.from_api() both represent 'no status checks
  configured' as None. The mismatch meant any fully-compliant branch under strict: true showed
  permanent 1-change drift and triggered an unnecessary

PUT on every single apply -- confirmed live: 'repo-policy plan' kept reporting 'Required status
  checks None -> required=[]' against a repo that had no status checks configured at all, before and
  after apply.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


## v0.1.1 (2026-09-19)


## v0.1.0 (2026-09-19)

### Bug Fixes

- Catch missing git binary in _resolve_repo
  ([`3337879`](https://github.com/shipsolid/repo-policy/commit/33378798cde8acd8de36573b406fcd8ba09a2346))

subprocess.run raised an uncaught FileNotFoundError when git isn't on PATH (plausible for the
  pip-installed CLI run outside the Docker Action) and no --repo/GITHUB_REPOSITORY was supplied,
  instead of the intended click.ClickException.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Fail fast with a clear error when no GitHub token is configured
  ([`ec113c5`](https://github.com/shipsolid/repo-policy/commit/ec113c552fcf599551ed6289a6c39423a02866e9))

_resolve_token silently fell back to an empty string, so a missing token sent 'Authorization: Bearer
  ' on every API call and surfaced as a generic 401 deep inside _request instead of an actionable
  message before any request was made.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Paginate list_rulesets() using GitHub's Link header
  ([`2c309da`](https://github.com/shipsolid/repo-policy/commit/2c309daa412a950275e4faa476c0b8141790da54))

Rulesets past page 1 were invisible to find_ruleset_by_name and prune_rulesets, since
  list_rulesets() issued a single unpaginated GET. Now requests per_page=100 and follows rel="next"
  links until exhausted.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Preserve unmodeled review/status-check fields on apply
  ([`775888f`](https://github.com/shipsolid/repo-policy/commit/775888f0b6e2503ec2fa0e8667bee5988c5671d7))

pull_requests.to_branch_protection() and status_checks.to_branch_protection() hardcoded
  dismiss_stale_reviews, require_last_push_approval, and required_status_checks.strict to False on
  every call. Since apply_branch rebuilds these nested objects in full whenever ANY declared field
  changes, a targeted edit to e.g. allow_force_push silently reset any of these three settings a
  human had configured manually on GitHub, contradicting this module's own docstring and the
  README's managed-scope promise.

Both functions now take the current GET payload and read these unmodeled fields through from it
  (falling back to False only on first-ever creation), matching the pattern already used for
  enforce_admins/restrictions.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Replace bare assert with explicit errors in prod code paths
  ([`46f08a0`](https://github.com/shipsolid/repo-policy/commit/46f08a0a0c192b43a02db214d22844d2daca710a))

Bare asserts are stripped entirely under python -O, silently removing the invariant checks they were
  meant to enforce -- and this project's own AGENTS.md convention calls for explicit error handling.
  Replaces: - 5 sites in GitHubClient (put/list/get/create/update) with a shared _expect_response()
  helper that raises GitHubAPIError. - 2 sites in branch_protection.py/rulesets.py's
  to_api_payload() with a ValueError naming the violated contract (resolved.pull_requests must come
  from diff.resolve_desired()).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Retry HTTP 429 responses in GitHubClient
  ([`4c538e1`](https://github.com/shipsolid/repo-policy/commit/4c538e1c25f20d265c364baa936b87ad2a53ee89))

GitHub's secondary rate limiting and abuse-detection responses return 429, which the retry predicate
  never matched (it only checked 403-with- 'rate limit'-text and >=500). A 429 raised GitHubAPIError
  immediately instead of backing off -- exactly the case the retry loop exists for.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Share one ruleset-list fetch across apply/audit/prune
  ([`ae23abb`](https://github.com/shipsolid/repo-policy/commit/ae23abb87acda3664dea04f4f3e502b6fbe6c4e6))

find_ruleset_by_name() previously called list_rulesets() fresh on every invocation, so a single
  'repo-policy apply' run against N ruleset-enforced branches issued N+1 identical GET /rulesets
  calls, and a strict-mode apply issued yet another for prune_rulesets right after. Added
  prefetch_rulesets() (computes the list once, only when actually needed) and threaded an optional
  rulesets_cache through fetch_current/plan_branch/apply_branch/ apply_all/prune_rulesets/audit_all;
  the apply CLI command now fetches once and shares it with both apply_all and prune_rulesets. Also
  closes a real gap: strict-mode apply had zero test coverage before this commit.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Treat empty INPUT_CONFIG/INPUT_MODE as unset in the Action entrypoint
  ([`fa4f81d`](https://github.com/shipsolid/repo-policy/commit/fa4f81d515b27a0268a3e5a8be2cd204d5535c54))

os.environ.get(key, default) only falls back when the env var is entirely absent; GitHub Actions
  sets INPUT_* vars to whatever the caller's 'with:' value resolves to, including an explicit empty
  string, which passed straight through as a confusing failure instead of honoring action.yml's
  documented defaults. Also adds the first test coverage for entrypoint.py, which had none.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Validate --repo format before splitting owner/name
  ([`058a8b1`](https://github.com/shipsolid/repo-policy/commit/058a8b1c41e0324bf27deb06047fb7e87dfaa59c))

A repo string with no '/' (a malformed --repo flag or GITHUB_REPOSITORY) crashed audit/plan/apply
  with an unhandled ValueError from the tuple unpack, duplicated across two call sites. Extracted a
  _split_repo() helper that raises a clean click.ClickException instead.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

### Chores

- Scaffold repo-policy package
  ([`add2293`](https://github.com/shipsolid/repo-policy/commit/add2293fa49dee656b1e1bffbb6465a3991a7364))

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

### Continuous Integration

- Add semantic-release automation with floating major tag
  ([`6c549c5`](https://github.com/shipsolid/repo-policy/commit/6c549c5cc14fa93dac013d3cbc04d3c6979269a4))

Routes the release tag through an env var instead of interpolating ${{ }} directly into the shell
  script, per the repo's workflow-injection guidance.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Add test/lint/typecheck workflow
  ([`8b22219`](https://github.com/shipsolid/repo-policy/commit/8b22219717de31b5a2b46bdc9d56afdb0cb1014a))

Also fixes the ruff/mypy findings this surfaced: Optional[X] -> X | None style throughout, import
  ordering, an unused unpacked variable in a test, and a PYI034 __enter__ return-type nit (kept as a
  string annotation since typing.Self needs Python 3.11+ and we target 3.10+).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

### Documentation

- Add README, CONTRIBUTING, and SECURITY
  ([`b270ac8`](https://github.com/shipsolid/repo-policy/commit/b270ac89a6892a7058efb79faa2b46ec65ad5453))

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

### Features

- Add apply engine with managed-scope and prune support
  ([`c982117`](https://github.com/shipsolid/repo-policy/commit/c982117b9f6b16e62172cbca0cf81ba51fac1c15))

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Add audit orchestration
  ([`e25c131`](https://github.com/shipsolid/repo-policy/commit/e25c1318e50eeaa781ffc3a041ae95115cb3537e))

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Add branch protection and required-signatures client methods
  ([`5914757`](https://github.com/shipsolid/repo-policy/commit/5914757f9b7c9515c47f248b9ef53cc134b73dc8))

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Add branch_protection API translator
  ([`75b2ed8`](https://github.com/shipsolid/repo-policy/commit/75b2ed88f1fe565ad019d1f9f305dd84d902ac9f))

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Add diff engine with managed-scope and strict resolution
  ([`2f68e61`](https://github.com/shipsolid/repo-policy/commit/2f68e61c60eefa770e5d01b1aa482126869e2712))

Fixes an add/remove misclassification for allow_force_push/allow_deletion, whose polarity is
  inverted relative to every other field (False means a restriction is present, not absent).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Add GitHub Action (Docker container action)
  ([`9dc68f1`](https://github.com/shipsolid/repo-policy/commit/9dc68f103b11935730cf45bc634ff22a849688a1))

Copies README.md into the build context too — hatchling's readme field validation fails the build
  otherwise.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Add GitHubClient with retrying request core
  ([`d58ca80`](https://github.com/shipsolid/repo-policy/commit/d58ca8046a3406309e2bb1efea7a1e633645026d))

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Add human-readable plan rendering
  ([`9f7c44f`](https://github.com/shipsolid/repo-policy/commit/9f7c44f176fbbeb92c090f7498fb5719dd4c1824))

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Add policy.yml loader with validation errors
  ([`aaee7b5`](https://github.com/shipsolid/repo-policy/commit/aaee7b5cfb0ff0ccf484bba8a094d89c7638c637))

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Add PolicyConfig models
  ([`2320da0`](https://github.com/shipsolid/repo-policy/commit/2320da0c801206b7b9acd95dc1f2afd78d3d7a0a))

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Add repo-policy CLI with validate/audit/plan/apply
  ([`6ea9217`](https://github.com/shipsolid/repo-policy/commit/6ea9217e4381d9ff24e208f5f8664d4f40ee9d87))

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Add ruleset API translator
  ([`2e7e411`](https://github.com/shipsolid/repo-policy/commit/2e7e411b90dd6f81c74e6e0688a6a102dc4ae0e6))

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Add ruleset CRUD to GitHubClient
  ([`4dc5765`](https://github.com/shipsolid/repo-policy/commit/4dc576532cb6badc93d1ad92915948562526ea19))

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Add shared pull_requests and status_checks translators
  ([`50c7417`](https://github.com/shipsolid/repo-policy/commit/50c7417b071f49cc2929572790e97309480ce5e9))

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

### Testing

- Add cross-backend field-parity guard
  ([`d63a39c`](https://github.com/shipsolid/repo-policy/commit/d63a39c68b064ed32dac606c0e9bef46a35cf5ca))

branch_protection.py and rulesets.py each hand-write their own payload translation with no shared
  source of truth between them -- the structural reason the previous commit's clobber bug existed in
  only one backend with zero test coverage. A full unification refactor is more risk than this
  warrants right now; this parametrized test is the cheaper guardrail: it fails loudly if a future
  field is wired into only one backend.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Add idempotency guarantee for apply
  ([`102505c`](https://github.com/shipsolid/repo-policy/commit/102505c1656308bb18784beb0327eed7f6f4b961))

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
