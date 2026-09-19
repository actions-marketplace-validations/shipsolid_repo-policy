# CHANGELOG


## v0.4.5 (2026-09-19)

### Bug Fixes

- Clear_restrictions: false no longer reports permanent phantom drift
  ([`73bf4af`](https://github.com/shipsolid/repo-policy/commit/73bf4afe95a4fecd420a4aaf31b30c392604d5e7))

clear_restrictions=False means "preserve whatever restriction is currently there" -- not "the branch
  must have a restriction". When current.clear_restrictions is True (no live restriction exists at
  all), there is nothing to preserve: branch_protection.to_api_payload's restrictions field
  collapses to None whether resolved.clear_restrictions is True or False, since
  _restrictions_payload(None) is None either way. diff() still reported this as a real Change every
  run, so a branch declaring clear_restrictions: false with no existing restriction could never
  reach a compliant state -- apply "succeeded" but sent the identical payload clear_restrictions:
  true would have, and the next audit reported the same drift again.

This is a narrower, asymmetric case than the "both empty" fix in d76c30c: the reverse direction (an
  existing restriction actually being cleared) is still correctly reported as real, applicable
  drift.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Diff() treats both-empty compound fields as equal, not just raw-equal
  ([`eb88a7b`](https://github.com/shipsolid/repo-policy/commit/eb88a7b21d91e78e45b67badb21dd7d3768ff7ca))

status_checks: {required: []} (declared empty) and status_checks undeclared both produce the exact
  same API payload -- to_branch_protection/ to_ruleset_rule return None for an empty required list
  either way -- but resolve_desired() sets resolved.status_checks to a real StatusChecksPolicy
  instance in the first case, while branch_protection.from_api/rulesets. from_api represent "nothing
  configured" as None. Raw `==` treats these as different, so diff() reported permanent phantom
  drift and apply_branch re-issued a no-op API call on every single run for a branch declaring an
  empty status_checks block.

Same failure mode for pull_requests: `{required: false, approvals: 5}` never raw-equals the
  canonical "nothing configured" PullRequestPolicy (approvals/code_owner_review differ), even though
  both produce an identical None payload once required is False --
  to_branch_protection/to_ruleset_rule never look at the other sub-fields in that case.

diff()'s per-field comparison now also treats two values as equal when both are "empty" per the
  field's own existing _is_empty() semantics (already used for add/remove/modify classification) --
  a no-op for every plain boolean field, since raw equality already catches those; it only changes
  behavior for the two compound types where "empty" isn't a single canonical value.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Preserve unmanaged rule types on ruleset updates
  ([`31daf75`](https://github.com/shipsolid/repo-policy/commit/31daf75472016e0f2a694418deb926235ceda5ef))

Broader version of d7a82af's enforcement/bypass_actors gap: to_api_payload() rebuilt the entire
  `rules` array from scratch, containing only the 6 rule types repo-policy models (pull_request,
  required_status_checks, required_signatures, required_linear_history, non_fast_forward, deletion).
  GitHub Rulesets support many more (commit_message_pattern, tag_name_pattern, merge_queue,
  workflows, code_scanning, file_path_restriction, ...) -- any human-added rule of one of those
  types was silently dropped the next time repo-policy touched that ruleset for an unrelated,
  modeled-field change, with no warning from diff/plan/audit since none of them are modeled fields.

Now carries forward any rule whose type isn't in the newly-introduced _MANAGED_RULE_TYPES set,
  verbatim, alongside rebuilding the ones repo-policy actually manages.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Repo-settings CLI output no longer overstates or hides drift
  ([`cd07043`](https://github.com/shipsolid/repo-policy/commit/cd07043e710b0f82d7d4d6308465e88930dd52e8))

Two related bugs in how cli.py surfaces RepoSettingsResult:

1. apply's "repo settings: applied N change(s)" counted every entry in result.changes, including
  ones that ended up in result.unavailable (a 422 during apply -- distinct from result.applied
  itself, which was already fixed in be11aa8 to exclude them from the pass/fail boolean, but the
  printed count still didn't). A partial success (1 of 2 changes landed) printed "applied 2
  change(s)" right next to the "unavailable" line contradicting it.

2. _run_check (audit/plan) only reported repo_settings_result.unavailable when result.changes was
  also non-empty. A repo-setting that's declared but structurally ineligible (e.g.
  private_vulnerability_reporting on a repo that doesn't support it) with zero other drift was
  silently dropped entirely -- audit printed "compliant" and exited 0 even though that part of the
  policy can never actually be satisfied.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Restore retry for idempotent POST calls, keep it off only for create_ruleset
  ([`14fff26`](https://github.com/shipsolid/repo-policy/commit/14fff2672b2788a673406967942b73f61d8b84fb))

Regression in f2c3dea's non-idempotent-POST guard: it blocked retries for EVERY POST, but
  set_required_signatures's enable path is also a POST and IS idempotent (repeating it is a no-op)
  -- a transient 5xx on that call now aborted the whole apply run instead of retrying, while the
  functionally identical PUT-based enable_vulnerability_alerts() etc. would have retried and likely
  succeeded.

_request() now takes an explicit idempotent=True default; only create_ruleset (the one call that
  actually creates a new resource each time) opts out with idempotent=False. Every other call, POST
  or not, retries on 5xx as before this was ever touched.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Stop YAML 1.1's yes/no/on/off from silently coercing to booleans
  ([`8c9d322`](https://github.com/shipsolid/repo-policy/commit/8c9d3223bc1c1637511254690d2c7a32916a62dd))

yaml.safe_load's default resolver treats bare yes/no/on/off (any casing) as booleans, not just
  true/false -- confirmed: yaml.safe_load("no") returns False. A branch name or status-check context
  that happens to be one of those words (e.g. `branches: {no: {...}}`) was silently turned into a
  Python bool before pydantic ever validated it, surfacing as a confusing "Input should be a valid
  string" error on a dict key that never looks like what the user typed.

_StrictBoolLoader subclasses SafeLoader and removes only the y/Y/n/N/o/O implicit-resolver entries
  for the bool tag -- true/false (any casing) still resolve as booleans, nothing else changes. This
  is NOT yaml.load()'s usual security footgun: no constructors were added or changed, so it remains
  exactly as safe as SafeLoader against arbitrary object construction (verified:
  !!python/object/apply tags still raise ConstructorError).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Transform restrictions from GET shape to PUT shape before re-sending
  ([`78eba5f`](https://github.com/shipsolid/repo-policy/commit/78eba5fdf06c7c2c4adf71ee420f4ad3fbd545a3))

to_api_payload() re-sent current_raw["restrictions"] verbatim when clear_restrictions is False.
  GitHub's GET response shapes restrictions.users/teams/apps as arrays of full objects (login/slug
  plus other metadata); the PUT request body expects arrays of bare login/slug strings. Any branch
  with an existing push restriction and clear_restrictions left at its inherited managed-scope
  default (False) would 422 the entire PUT the next time ANY other declared field changed --
  aborting the whole apply run with GitHubAPIError, unrelated to what was actually being changed.

The existing tests never caught this because their current_raw fixtures already used the flat string
  shape instead of GitHub's real GET shape -- fixed those too, so they now exercise the actual
  transform.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

### Refactoring

- Dedupe repo-settings field groupings, fix resolve_desired's docstring
  ([`48418a4`](https://github.com/shipsolid/repo-policy/commit/48418a455b3b34b4d53493069c1f75dfb81be630))

apply_repo_settings() re-derived which Change.field values belong to the "flat settings" and
  "security_and_analysis" PATCH groups via inline tuple literals, byte-identical to but independent
  of policies/repo_settings.py's _FLAT_FIELDS/_SECURITY_AND_ANALYSIS_FIELDS (the ones
  diff_flat_settings/ diff_security_and_analysis already use to detect drift in the first place).
  Currently in sync, but a future field added to one and not the other would mean plan/audit
  correctly show a field needing a change while apply silently excludes it from the PATCH payload --
  reads as success, never sent to GitHub. Now imports and reuses the same tuples.

Also corrects resolve_desired()'s docstring, which claimed the result "always has every field
  concretely set" -- status_checks' own permissive value is deliberately None (matching how from_api
  represents "nothing configured"), so that one field is the documented exception, not an oversight
  diff() has to work around.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


## v0.4.4 (2026-09-19)

### Bug Fixes

- _is_empty dispatches on isinstance, not a shared .required attribute name
  ([`2eacaa5`](https://github.com/shipsolid/repo-policy/commit/2eacaa5b0092719655753b47d69216995ff52460))

hasattr(value, "required") was standing in for "is this a PullRequestPolicy or a StatusChecksPolicy"
  -- a naming coincidence, not a type check. A future value type exposing an unrelated .required
  attribute wouldn't just be misclassified, it would crash: the isinstance(required, bool) branch
  calls len() on the fallback path, which raises TypeError for anything that's neither bool nor
  sized. Explicit isinstance checks preserve identical behavior for both current cases.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Honor GitHub's Retry-After header instead of blind exponential backoff
  ([`f2c3dea`](https://github.com/shipsolid/repo-policy/commit/f2c3deafb6604c260bcc3bd7662c177eee96504d))

The fixed exponential backoff (1s/2s/4s by default) ignored Retry-After on secondary-rate-limit
  429/403 responses, so a sustained rate-limit window could exhaust all retry attempts well before
  GitHub's own requested wait cleared, aborting the run when a header-aware wait would have
  succeeded.

Deliberately does not honor X-RateLimit-Reset (the primary rate limit) -- that reset can be up to an
  hour away, and silently blocking a CLI invocation for that long is a product decision (fail fast
  with a clear error vs. block), not a pure reliability fix. Falls back to the existing exponential
  backoff when Retry-After is absent or unparseable.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Preserve enforcement mode and bypass_actors on ruleset updates
  ([`d7a82af`](https://github.com/shipsolid/repo-policy/commit/d7a82af5102f38869144f636e40a57a850c07483))

Same bug class as the earlier strict_required_status_checks_policy fix (f291a05), and it wasn't
  fully closed: to_api_payload() also hardcoded "enforcement": "active" unconditionally and never
  carried bypass_actors through at all. Since ruleset PUT/POST is a full-object replace, either gap
  meant an unrelated declared change (e.g. bumping approvals) would silently re-activate a ruleset a
  human had flipped to "evaluate" (dry-run) mode, or wipe out bypass permissions a security team had
  configured -- neither ever surfaced by diff/plan/audit, since neither field is modeled.

Both are now read through from current_raw the same way, defaulting to "active"/[] only when there's
  no current state to read (first creation).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Pullrequestpolicy/statuscheckspolicy are frozen, fixing Change's hashability for pull_requests
  ([`72fcafb`](https://github.com/shipsolid/repo-policy/commit/72fcafbb2ab563244816c714ad3f8ea5d0f548ff))

Change is @dataclass(frozen=True), whose auto-derived __hash__ requires every field to be hashable
  -- but current_value/desired_value can hold PullRequestPolicy/StatusChecksPolicy instances, and
  plain (non-frozen) pydantic BaseModel instances aren't hashable. Nothing currently hashes a
  Change, so this was latent, but a real footgun for future code (e.g. dedup via a set).

Made both models frozen: pydantic's frozen models are both immutable and (when every field is
  hashable) hashable, matching Change's own frozen, snapshot-value-object nature. Confirmed no code
  path mutates either model in place anywhere in this codebase, so this is behavior-preserving.

Fully fixes it for pull_requests (all-scalar fields). status_checks stays technically unhashable
  regardless -- StatusChecksPolicy.required is a list, and a list field makes a frozen model's
  derived __hash__ raise TypeError just the same. Freezing it still adds the immutability guarantee;
  changing `required` to a tuple to close the remaining gap would ripple into a public field's type
  and at least one test's equality assertion for a still-latent, never-triggered edge case -- left
  alone as not worth that footprint.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

### Documentation

- Replace dangling plan-doc references with commit hashes
  ([`3cd2728`](https://github.com/shipsolid/repo-policy/commit/3cd2728799abf6978463d51f4fdb5b2dfbf6849e))

Both comments cited docs/superpowers/plans/2026-09-19-*.md files that no longer exist -- this
  project deletes plan docs once the work they guided ships, which leaves any comment pointing at
  one a dead end. Commit hashes are durable; point to those instead.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

### Refactoring

- Dedupe the enforce_admins/lock_branch/etc. permissive-value table
  ([`e83920b`](https://github.com/shipsolid/repo-policy/commit/e83920b9b7baa1d43baddaca7b6e31e25172d706))

The permissive (no-op) value for the 5 ruleset-unsupported fields (enforce_admins,
  required_conversation_resolution, lock_branch, allow_fork_syncing, clear_restrictions) was
  hand-copied in 3 places: models._RULESET_UNSUPPORTED_FIELDS (the validator's source of truth),
  diff._SCHEMA_DEFAULTS, and twice more inline in policies/rulesets.py's from_api(). All three now
  read from models._RULESET_UNSUPPORTED_FIELDS -- the only module with no dependency on the other
  two, so no import cycle. Left the broader "fully permissive BranchPolicy/PullRequestPolicy
  literal" consolidation alone (policies/branch_protection.py and rulesets.py's from_api(None), and
  pull_requests.py's from_*(None)) -- unlike this 5-key subset, those also share a nested
  PullRequestPolicy instance, and having multiple BranchPolicy objects reference the exact same
  PullRequestPolicy by identity would reintroduce the shared-mutable-state class of bug the
  _merge_pull_requests fix (see the resolve_desired commit) specifically eliminated. Not worth that
  risk for a cosmetic DRY win on rarely-changed, self-documenting literals.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Derive BranchResult.applied instead of setting it at each call site
  ([`5a09d1c`](https://github.com/shipsolid/repo-policy/commit/5a09d1c55351702390ea9c3c226080304d63cc0e))

applied was always exactly bool(changes) at both of BranchResult's construction sites -- now a
  @property, matching the pattern already used for AuditResult.compliant. Behavior-preserving: no
  test or caller ever passed applied= explicitly.

Skipped a related dedup: having apply_all batch detect_stale_branch_protection once (mirroring
  audit_all) and pass membership into apply_branch, instead of apply_branch re-deriving the
  single-branch predicate inline. Reverted after confirming it breaks apply_branch's
  standalone-callable contract --
  test_apply_branch_flags_stale_branch_protection_for_ruleset_enforced_branch calls apply_branch
  directly (not through apply_all) and relies on it self-detecting staleness. The two predicates
  read identically but intentionally live at different scopes; not a safe dedup.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Extract _build_client, shared by _run_check and apply
  ([`30905b1`](https://github.com/shipsolid/repo-policy/commit/30905b11698e82c170189190cc474180220b301b))

apply() re-implemented _run_check's exact load_policy -> _resolve_repo -> _split_repo ->
  GitHubClient(...) setup sequence inline instead of sharing it, a real drift risk (e.g. a future
  GitHubClient constructor change or _resolve_token behavior change would need updating in two
  places). Extracted _build_client(config_path, repo, token) -> (PolicyConfig, str, GitHubClient),
  covering exactly the setup with no command-specific behavior; ConfigError and click.ClickException
  both still propagate uncaught so each caller keeps its own exit-code idiom (_run_check returns
  EXIT_CONFIG_ERROR, apply calls sys.exit(EXIT_CONFIG_ERROR)).

Caught during this refactor: `with client:` (no `as`) doesn't rebind to whatever __enter__() returns
  -- harmless in production since GitHubClient.__enter__ returns self, but it silently broke every
  mocked CLI test, which configure behavior on mock_client_cls.return_value.__enter__ .return_value
  and expect the code under test to operate on that object. Fixed with `with client as client:`,
  caught by running the full suite before committing.

Skipped per independent review: sharing the --config/--repo/--token option decorator across
  audit/plan/apply (inert boilerplate at 3 call sites, not worth a shared decorator) and merging
  render_plan/render_repo_settings (the two functions differ in load-bearing ways -- compliant-field
  listing, unavailable-section, strict-vs-tolerant label lookup -- that a shared abstraction would
  paper over).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Render.py drives field iteration from diff._FIELDS, labels fail safe
  ([`2e4f49a`](https://github.com/shipsolid/repo-policy/commit/2e4f49a1c0a135d3e13a864a3fa5781aa541e669))

_LABELS was a hand-maintained duplicate of diff._FIELDS' key set with no safety net -- render_plan
  indexed it with a bare _LABELS[change.field], so a future BranchPolicy field added to _FIELDS
  without a matching _LABELS entry would raise KeyError the first time it produced a Change. Now
  iterates _FIELDS directly (matching render_repo_settings' already-tolerant
  _REPO_SETTINGS_LABELS.get(field, field) pattern) and falls back to the raw field name instead of
  crashing.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Reuse _unwrap for GitHub's {"enabled": bool} response shape
  ([`37e4829`](https://github.com/shipsolid/repo-policy/commit/37e4829c290a06867dc5ee261572decfc04db14c))

get_required_signatures, get_automated_security_fixes, and get_private_vulnerability_reporting each
  hand-rolled their own inline .get("enabled", default) unwrap instead of reusing _unwrap, which
  already existed for exactly this GitHub response convention but lived in
  policies/branch_protection.py, several layers away from github_client.py's response parsing.
  Relocated _unwrap into github_client.py (where 3 of its 4 use sites already lived, and where it
  belongs conceptually -- parsing GitHub's raw JSON shapes); policies/branch_protection.py now
  imports it.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


## v0.4.3 (2026-09-19)

### Bug Fixes

- Detect and clean up stale rules when a branch's enforcement mode switches
  ([`f9e3217`](https://github.com/shipsolid/repo-policy/commit/f9e32178ec1d1ae776546a356d6a5e3e9b24c6df))

Switching enforcement: ruleset -> branch_protection left the orphaned repo-policy:<branch> ruleset
  permanently un-prunable (prune_rulesets keyed on branch-name presence, not current enforcement) --
  now fixed, since ruleset ownership is unambiguous via the naming convention. Switching
  branch_protection -> ruleset left the old classic branch protection fully active and invisible to
  audit, which reported the branch compliant -- classic branch protection has no ownership marker
  (same reason ARCHITECTURE.md already documents for branch removal), so this direction is detected
  and reported rather than auto-deleted.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Get_private_vulnerability_reporting fails closed, and GitHubClient stops closing injected clients
  ([`9ac408c`](https://github.com/shipsolid/repo-policy/commit/9ac408c2cf5460ecb6024922c15315adb58f71de))

get_private_vulnerability_reporting() defaulted a missing 'enabled' key to True; the structurally
  identical get_automated_security_fixes() defaults to False. Matches that pattern now -- failing
  open in the riskier direction was wrong for a security setting.

Also fixes close()/__exit__ unconditionally closing self._client even when it was injected via the
  constructor's client= parameter, which would break a caller sharing one httpx.Client across
  multiple GitHubClient wrappers. Landed together since both are small fixes to the same file.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Give an actionable message when policy.yml's top level isn't a mapping
  ([`fa1ccd8`](https://github.com/shipsolid/repo-policy/commit/fa1ccd881b36193e975379c2e776aff1b615a80a))

pydantic reports a root-level type error with loc == (), which rendered as a bare ' - : <message>'
  bullet with no location hint.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Preserve strict_required_status_checks_policy on ruleset-enforced branches
  ([`f291a05`](https://github.com/shipsolid/repo-policy/commit/f291a055927c8301540a7810026567a6dc92230a))

The ruleset backend hardcoded strict_required_status_checks_policy: False on every apply, silently
  disabling a human-configured 'require branches up to date' setting whenever any other declared
  field changed. The branch_protection backend already reads this through from current state for
  exactly this reason (see docs/test-strategy.md bug #1) -- this mirrors that fix to the ruleset
  backend.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Re-validate resolve_desired()'s merged policy and merge pull_requests per field
  ([`47456f3`](https://github.com/shipsolid/repo-policy/commit/47456f36fc399e201d386d079276c712f34b81f7))

model_copy(update=...) never re-runs BranchPolicy's model_validators, so managed-scope mode could
  reconstruct the exact allow_fork_syncing/lock_branch combination the allow_fork_syncing validator
  exists to reject (a recurrence of a bug already fixed once via live-repo testing, see
  docs/test-strategy.md bug #4) -- now caught and raised as PolicyResolutionError instead of
  shipping to the GitHub API. Also fixes pull_requests being merged as one atomic block: a partial
  declaration (e.g. approvals only) silently reset
  code_owner_review/dismiss_stale_reviews/require_last_push_approval to pydantic's class defaults
  instead of preserving current state -- now merged field-by-field via model_fields_set, matching
  every other BranchPolicy field's managed-scope behavior.

Also fixes clear_restrictions being classified with the wrong add/remove polarity in plan/audit
  output -- it shares allow_force_push/allow_deletion's true-means-permissive polarity but was
  missing from _INVERTED_FIELDS. Landed together since both are in diff.py.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Reject secret_scanning_push_protection without secret_scanning at config time
  ([`0558656`](https://github.com/shipsolid/repo-policy/commit/0558656c4e1bc83ec89c274f473975536bec8547))

Mirrors the existing automated_security_fixes/vulnerability_alerts validator. Without it, declaring
  only secret_scanning_push_protection: true produced a real GitHub 422 at apply time, misreported
  via the same 'unavailable on this repository' message used for genuinely-unlicensed GHAS -- hiding
  an actionable config fix as if nothing could be done.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Stop CLI setup errors from colliding with the policy-drift exit code
  ([`762299d`](https://github.com/shipsolid/repo-policy/commit/762299dbc6e535d89797a86abdfc0ea4e4c016f0))

click.ClickException defaults to exit_code=1, identical to this CLI's own EXIT_DRIFT -- a missing
  GITHUB_TOKEN, an unresolvable --repo, or a malformed --repo flag were all indistinguishable from
  real policy drift for any CI pipeline branching on exit code.
  _resolve_token/_resolve_repo/_split_repo now raise a _ConfigClickException subclass that forces
  exit_code=2. Also fixes _resolve_repo() silently ignoring a failing git invocation's returncode
  and parsing whatever stdout happened to contain regardless.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Stop retrying non-idempotent POST requests on 5xx
  ([`1b5719e`](https://github.com/shipsolid/repo-policy/commit/1b5719e7b77a0d24b02477cc4a2a25d110d7b367))

create_ruleset is a POST -- retrying it on a 5xx whose response was lost after GitHub already
  processed the request could create a duplicate repo-policy:<branch> ruleset.
  429/secondary-rate-limit responses still retry for every method, since GitHub rejects those before
  doing any work.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Support disabling repo-settings toggles and stop misreporting applied
  ([`be11aa8`](https://github.com/shipsolid/repo-policy/commit/be11aa8d06263c7615837a36302d9c16904eec5e))

vulnerability_alerts/automated_security_fixes/private_vulnerability_reporting could only ever be
  enabled -- github_client.py had no DELETE-endpoint method for any of them, so apply_repo_settings
  always called the enable path regardless of the declared direction. Declaring false on an
  already-enabled repo was a silent no-op reported as success, with audit re-flagging the same drift
  forever. GitHub supports DELETE on all three endpoints (confirmed by the existing enable/disable
  pair already implemented for required_signatures); this adds the missing disable path.

Also fixes RepoSettingsResult.applied, which was bool(result.changes) and stayed True even when the
  only detected change immediately moved to result.unavailable (e.g. a 422 from unlicensed GHAS) --
  apply printed 'applied 1 change(s)' and 'unavailable' for the same field in the same run. Landed
  together since both touch apply_repo_settings's final lines.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

### Chores

- Mark fix-audit-findings plan tasks complete
  ([`20078d5`](https://github.com/shipsolid/repo-policy/commit/20078d587acd3f9d6351fc263978e4a2dc945f07))

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Remove internal planning doc for the audit-findings fix round
  ([`ef75e8f`](https://github.com/shipsolid/repo-policy/commit/ef75e8f10c1719fc6f2fd623cd12608753778e14))

Matches this project's established convention of removing docs/superpowers/plans/*.md once the work
  they guided has shipped (see commit cc06ebf).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


## v0.4.2 (2026-09-19)

### Bug Fixes

- Don't attempt ruleset-branch creation with a token that can't do it
  ([`46308ce`](https://github.com/shipsolid/repo-policy/commit/46308ce14e0e233ef7696e08f315b1e41a32bb05))

REPO_POLICY_E2E_TOKEN is scoped to Administration: Read and write only, which doesn't cover git
  ref/branch creation (that needs the separate Contents: Read and write permission). The first real
  CI run of the E2E workflow failed with 403 "Resource not accessible by personal access token" on
  the self-heal POST to create repo-policy-verify.

Bootstrapped the branch once, out of band, with a higher-privilege session (gh api ... git/refs).
  _ensure_ruleset_branch_exists now only verifies presence and fails with an actionable message if
  it's ever missing again, instead of attempting a create call the token's documented
  least-privilege scope can't perform.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

### Continuous Integration

- Add nightly/manual E2E workflow against the live fixture repo
  ([`9a7e203`](https://github.com/shipsolid/repo-policy/commit/9a7e203f7abc58b29438a8587de447ee69b32775))

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

### Documentation

- Record the automated E2E suite against the live fixture repo
  ([`463c3c5`](https://github.com/shipsolid/repo-policy/commit/463c3c5c4ff3a31f43475ea869dd2bb6cf63b852))

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

### Testing

- Add e2e fixture policy files modeled on this session's manual verification
  ([`9b8bf88`](https://github.com/shipsolid/repo-policy/commit/9b8bf886aaea0642750126831c845723be1a2083))

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Add e2e marker infrastructure and live fixture-repo connectivity check
  ([`30aca6e`](https://github.com/shipsolid/repo-policy/commit/30aca6e218c169f9e217259fa06cf82f1fc342cb))

Adds docs/superpowers/plans/2026-09-20-e2e-fixture-repo-testing.md, the pytest e2e marker (excluded
  by default via addopts), and tests/e2e/conftest.py's session-scoped live-repo fixtures against
  shipsolid/repo-policy-e2e-fixture.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Add full E2E lifecycle coverage against the live fixture repo
  ([`663d0b5`](https://github.com/shipsolid/repo-policy/commit/663d0b5d09389cd2356934665d0171ebe9c0c509))

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


## v0.4.1 (2026-09-19)

### Bug Fixes

- Correct allow_fork_syncing's permissive default from true to false
  ([`99fb988`](https://github.com/shipsolid/repo-policy/commit/99fb988ccd7c611c2afe2006911c5a7bfd0a9054))

Found via live-repo verification against a real GitHub repo (shipsolid/playground): GitHub silently
  discards allow_fork_syncing: true on any branch protection PUT where lock_branch is false --
  confirmed by pairing them (works) and unpairing them (silently resets to false) against the real
  branch-protection API. The old default of true meant ANY first-time apply against a
  previously-unprotected branch inherited lock_branch: false + allow_fork_syncing: true via
  resolve_desired()'s managed-scope current-state inheritance, and strict mode's schema-default
  injection had the identical problem for any branch that left the field undeclared -- neither path
  goes through model validation (Pydantic's model_copy() skips validators), so this couldn't have
  been caught by a validator alone. False is now the default everywhere: diff._SCHEMA_DEFAULTS, both
  backends' from_api(), and the ruleset-unsupported-fields validator's permissive-value entry. No
  longer inverted polarity -- removed from diff._INVERTED_FIELDS.

Known, expected gap closed by the very next commit: tests/test_models.py's
  test_branch_policy_rejects_allow_fork_syncing_under_ruleset still asserts the OLD non-permissive
  value (False) triggers ruleset rejection; it now needs True instead. Deliberately left red here
  since that test lives in this plan's Task 2 (the new lock_branch-pairing validator), not this
  task's file list -- fixed as Task 2 Step 1 before any new validator code is added.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

- Reject allow_fork_syncing: true without lock_branch: true
  ([`89e04f5`](https://github.com/shipsolid/repo-policy/commit/89e04f549a353243f197a4efba0d316d53da3d41))

Defense-in-depth alongside Task 1's default-value fix: Pydantic's model_copy() (used throughout
  diff.resolve_desired()) skips validators, so this new validator only catches EXPLICIT policy.yml
  declarations of the broken combination -- it cannot see values injected by schema defaults or
  current-state inheritance, which is why Task 1's fix to the underlying representation was the
  primary correction and this is the secondary one. Scoped to enforcement: branch_protection only --
  under enforcement: ruleset, allow_fork_syncing: true is the allowed permissive no-op value
  (existing _reject_ruleset_unsupported_fields validator), and lock_branch: true is itself rejected
  there, so requiring the pairing under ruleset enforcement would be unsatisfiable.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

### Documentation

- Record the allow_fork_syncing bug as the 4th live-testing find
  ([`2bbe0c5`](https://github.com/shipsolid/repo-policy/commit/2bbe0c59213cd225e4df213265988cdc76075586))

docs/test-strategy.md's "three real bugs" section becomes four, matching its existing tone and
  structure. ROADMAP.md's Now table gets a row matching the established Phase 1/2/3 convention.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


## v0.4.0 (2026-09-19)

### Documentation

- Document clear_restrictions and the closed repo_security gap
  ([`376090b`](https://github.com/shipsolid/repo-policy/commit/376090bb654ed4e5ac6921a941591f0cb277a663))

ARCHITECTURE.md's Domain Model and Apply Safety Model sections corrected -- restrictions is no
  longer in the unmodeled-fields list. ROADMAP.md's Now table gets a row matching the Phase 1/2
  convention.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

### Features

- Model clear_restrictions, closing the last repo_security field gap
  ([`9abd10a`](https://github.com/shipsolid/repo-policy/commit/9abd10a663aec1d9e3fa13d709af34dcfa13bcf4))

Closes the final field-level gap against the sibling repo_security tool's baseline: GitHub
  branch-protection restrictions (push allowlist), which repo_security unconditionally clears to
  null on every apply. repo-policy only supports declaring the clear -- not setting an arbitrary
  allowlist, since neither repo-policy's schema nor repo_security itself ever manages one.
  Branch_protection-only, guarded by the same ruleset-unsupported-fields validator as
  enforce_admins/ required_conversation_resolution/lock_branch/allow_fork_syncing.

Also excludes clear_restrictions from test_policies_parity.py's generic BRANCH_PROTECTION_FIELDS
  parametrize (mirroring the existing signed_commits exclusion): that test calls to_api_payload with
  current_raw=None for both sides of the comparison, so there's no existing restrictions value to
  preserve either way -- clear_restrictions True and False both collapse to restrictions: None
  there, a real blind spot in that specific test setup, not a code bug. The actual round-trip is
  proven by two dedicated tests using realistic current_raw data. Plan doc updated to record this,
  found only by running the tests.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


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
