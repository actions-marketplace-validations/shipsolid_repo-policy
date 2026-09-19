# CI/CD Pipeline

## Pipeline Architecture

Two workflows run on every push to `main`:

| Workflow | File | Trigger | Purpose |
|---|---|---|---|
| CI | `.github/workflows/ci.yml` | push to `main`, every PR | `ruff check`, `mypy`, `pytest` |
| Release | `.github/workflows/release.yml` | push to `main` | version bump, changelog, git tag, floating major tag, PyPI publish |

Both are confirmed running green on real GitHub Actions runners, not just locally — see
`docs/test-strategy.md`.

## Branch Strategy

Single `main` branch. No release branches; every release is cut directly from `main` by
`python-semantic-release` reading Conventional Commits history since the last release tag.

## Release Process

1. A commit lands on `main` (directly, or via a merged PR).
2. `python-semantic-release` inspects commits since the last release tag:
   - `feat: ...` → minor bump
   - `fix: ...` → patch bump
   - `feat!: ...` or a `BREAKING CHANGE:` footer → major bump
   - `chore:` / `docs:` / `test:` / `ci:` → no release
3. If a release is warranted, it bumps `pyproject.toml`'s `project.version` **and**
   `src/repo_policy/__init__.py`'s `__version__` (via `version_variables` in
   `[tool.semantic_release]` — both must be listed, or they silently diverge; this happened once
   in production, see `docs/test-strategy.md`), regenerates `CHANGELOG.md`, commits as
   `chore(release): {version} [skip ci]`, and tags `v{version}`.
4. The floating major tag (`v0` until a `1.0.0` ships — see README) is force-moved to point at the
   new release tag.
5. The package is published to PyPI via trusted publishing (OIDC) — no long-lived API token stored
   in the repo.

## A step-ordering bug this pipeline shipped once

Steps 4 and 5 are independent — nothing about moving the floating tag depends on PyPI publishing
succeeding, or vice versa. The workflow originally ran them in the order 5-then-4: when PyPI
publish failed (as it did on every release before trusted publishing was configured), step 4 was
skipped along with it, silently. `uses: shipsolid/repo-policy@v0` was broken for every consumer
across several releases, and nothing in the workflow's status said so — the job still reported
success up to the point PyPI's own step failed.

**The fix:** run the tag-move step before the PyPI-publish step. Two independent side effects of
one event should never be ordered such that one's failure can silently skip the other.

## PyPI Trusted Publishing

Configured at pypi.org → Publishing → pending/active publisher:

| Field | Value |
|---|---|
| PyPI project name | `repo-policy` |
| Owner | `shipsolid` |
| Repository | `repo-policy` |
| Workflow | `release.yml` |
| Environment | *(none)* |

No PyPI API token is stored anywhere in this repository, by design.

**Status:** working as of v0.1.3. The trusted publisher above wasn't registered on pypi.org until
after v0.1.2 shipped, so `v0.1.0`, `v0.1.1`, and `v0.1.2` each failed at the PyPI-publish step with
`invalid-publisher` (GitHub's OIDC token had no matching publisher to exchange against — trusted
publishing has to be pre-registered on PyPI before the first attempt, it isn't provisioned by
`permissions: id-token: write` alone). Those three git tags and GitHub releases exist but were
never published to PyPI, and — since PyPI never allows re-uploading a consumed version number —
never will be; `pip install repo-policy` starts at `0.1.3`. `v0.1.3` onward publish cleanly.

## Rollback

There is no manual rollback step for a bad release — semantic-release doesn't support "undo." To
recover from a bad release:

1. Fix forward with a new `fix:` commit; it produces a new, higher version immediately.
2. If the bad version must not be installed, [yank it on PyPI](https://pypi.org/manage/project/repo-policy/releases/)
   (the version number itself can never be reused, even after yanking).
3. If the floating `v0` tag now points at a bad commit and a fix hasn't shipped yet, it can be
   moved back manually: `git tag -f v0 <last-good-tag> && git push origin v0 --force`.

## Known Platform Constraint: `secrets.GITHUB_TOKEN` Cannot Run This Action

Confirmed against a real workflow run in a real repository: the GitHub Actions auto-generated
`secrets.GITHUB_TOKEN` has no permission scope covering repository administration (branch
protection or rulesets), under any `permissions:` block configuration. Every consumer of
`shipsolid/repo-policy@v0` must supply a real PAT via a custom repository secret and pass it as
`env: GITHUB_TOKEN: ${{ secrets.<YOUR_SECRET_NAME> }}` on the step — see the README's GitHub
Action example. This is a GitHub platform limitation, not something this pipeline or the Action's
`action.yml` can work around.
