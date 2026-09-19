# CHANGELOG


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
