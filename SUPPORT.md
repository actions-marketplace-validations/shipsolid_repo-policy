# Support

## Getting Help

- **Bug reports and feature requests:** open a [GitHub Issue](https://github.com/shipsolid/repo-policy/issues).
- **Security vulnerabilities:** do not open a public issue — see [SECURITY.md](SECURITY.md).
- **Usage questions:** check [FAQ.md](FAQ.md) and [docs/troubleshooting.md](docs/troubleshooting.md)
  first; most first-time setup problems (especially GitHub Action token errors) are already
  covered there.

## Before Filing an Issue

Include:

- The exact command run (`repo-policy plan --repo ...` etc.) and its full output.
- Your `policy.yml` (redact org/repo names if you'd rather not share them; it shouldn't contain
  secrets in the first place).
- Whether you're running the CLI directly or via the GitHub Action.
- repo-policy's version (`pip show repo-policy`) or the Action tag you're using.

## Response Expectations

This is a single-maintainer open-source project. There's no SLA. Security reports are
acknowledged within 5 business days per [SECURITY.md](SECURITY.md); everything else is
best-effort.
