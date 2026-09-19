# CHANGELOG


## v0.1.0 (2026-09-19)

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

- Add idempotency guarantee for apply
  ([`102505c`](https://github.com/shipsolid/repo-policy/commit/102505c1656308bb18784beb0327eed7f6f4b961))

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
