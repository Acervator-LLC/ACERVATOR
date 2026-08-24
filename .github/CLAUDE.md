# `.github/` — CLAUDE.md

This directory catalogues the project's **CI/CD and repository automation**. It
is **not** application code and **not** documentation — only files that configure
how the repo builds, tests, lints, releases, and accepts contributions belong here.

## What lives here

- `workflows/` — GitHub Actions pipelines (test, lint, build, release, scheduled jobs)
- linting / formatting / type-check config that CI runs
- issue and pull-request templates — `ISSUE_TEMPLATE/`, `PULL_REQUEST_TEMPLATE.md`
- `CODEOWNERS`, and contribution/automation config (e.g. Dependabot)

## What does NOT belong here

Application source (`src/`), tests (`tests/`), or documentation (`docs/`). If it
is not repository automation, it goes in the folder whose role it fills.

See the root [`CLAUDE.md`](../CLAUDE.md) for the two repository-wide hard rules:
every file must live in the folder that accurately represents its role, and
local/user-specific paths are forbidden — a portable generic is always used.
