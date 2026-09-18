# Contributing

Issues and pull requests are welcome. This is a hobby-scale project, so keep changes focused
and small where you can. Taking part means agreeing to the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Before you start

- Read the [README](README.md) setup section and get a run going locally — most changes here
  need the actual game or the fake plugin to verify against, not just tests.
- For anything beyond a small fix, skim the [design doc](docs/superpowers/specs/2026-09-17-jev-vampire-survivors-design.md)
  first. It documents the constraints this project works within (e.g. why raw numbers never
  reach Jev, why the plugin holds no strategy) and the reasoning behind them.

## Making changes

- **Brain (Python, `brain/`):** add or update tests under `brain/tests/` alongside any
  behavior change, and run the [checks](#checks) below before opening a PR. Tests marked `live`
  call the real TypeSafe API and need `TYPESAFE_API_KEY`; they aren't required to pass without
  a key, but do check they still make sense.
- **Plugin (C#, `mod/`):** the plugin is intentionally thin — if you're adding decision logic,
  it almost certainly belongs in the brain instead. After changing it, `scripts/deploy_mod.sh`
  and a manual smoke run (or at least a build with no exceptions at boot) is the only way to
  verify it; there's no C# test suite, by design (see the design doc's Testing section for why).
- **Question wording and thresholds** live only in `brain/jev_vs/questions.py` — keep it that
  way so it stays the one file worth reviewing for prompt changes.
- Match the existing code style in the file you're editing rather than introducing a new one.

## Checks

Three commands, all run from `brain/`:

```bash
cd brain                     # from the repository root
uv run ruff check .          # lint
uv run ruff format --check . # formatting (drop --check to apply it)
uv run pytest                # tests, offline by default
```

CI runs exactly these three on every pull request (and on every push to `main`), and nothing
else — so if they pass locally they pass on the PR. It installs with `uv sync --locked`
first, so if you add or bump a dependency, commit the updated `brain/uv.lock` with it. Ruff's
settings — line length, rule selection — live in `brain/pyproject.toml`; please change the
code rather than the rules to get a clean run.

**CI does not build the C# plugin.** Building it needs the game's own assemblies from your
Steam install, which are proprietary and can't be shipped to a runner, so the `mod/` half of
this repo is verified locally only: `scripts/deploy_mod.sh` to build and deploy, then a manual
smoke run of the game. A pull request that touches `mod/` should say in its description what
smoke run was done — which game version, how long it ran, and what you watched it do (menus,
a level-up, a game over) — because CI can tell you nothing about it.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/) with a component scope, written
in the imperative and describing the behavior rather than the diff. The scope is `brain` or
`mod`; repo-wide changes (docs, tooling) use no scope. Recent history is the reference:

```
feat(brain): give Jev xp, objective, and obstacle awareness plus varied character and stage picks
fix(mod): do not count a revived run twice against the run budget
test(brain): check the dashboard's four panels instead of the old name
docs: prep repo for open source (README, LICENSE, CONTRIBUTING, .env.example)
```

Nothing enforces this, and PRs aren't squash-renamed for it — it's just what the log looks
like, and it keeps the changelog easy to write.

## Pull requests

- Open the PR and fill in the [template](.github/PULL_REQUEST_TEMPLATE.md) — it asks for the
  same things this page does. For bugs and ideas, the
  [issue forms](.github/ISSUE_TEMPLATE/) are the fastest route.
- Describe what you tested it against (a real run, the fake plugin replay, or just the test
  suite) — this project has real physical/API side effects, so "it compiles" isn't much signal
  on its own.
- If you're changing behavior the [Known limitations](README.md#known-limitations) section
  calls out as unverified, please say so and how you verified it.
- User-visible changes are worth a line under `## [Unreleased]` in
  [`CHANGELOG.md`](CHANGELOG.md); internal refactors and test-only changes aren't.
