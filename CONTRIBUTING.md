# Contributing

Issues and pull requests are welcome. This is a hobby-scale project, so keep changes focused
and small where you can.

## Before you start

- Read the [README](README.md) setup section and get a run going locally — most changes here
  need the actual game or the fake plugin to verify against, not just tests.
- For anything beyond a small fix, skim the [design doc](docs/superpowers/specs/2026-09-17-jev-vampire-survivors-design.md)
  first. It documents the constraints this project works within (e.g. why raw numbers never
  reach Jev, why the plugin holds no strategy) and the reasoning behind them.

## Making changes

- **Brain (Python, `brain/`):** add or update tests under `brain/tests/` alongside any
  behavior change, and run `cd brain && uv run pytest` before opening a PR. Tests marked `live`
  call the real TypeSafe API and need `TYPESAFE_API_KEY`; they aren't required to pass without
  a key, but do check they still make sense.
- **Plugin (C#, `mod/`):** the plugin is intentionally thin — if you're adding decision logic,
  it almost certainly belongs in the brain instead. After changing it, `scripts/deploy_mod.sh`
  and a manual smoke run (or at least a build with no exceptions at boot) is the only way to
  verify it; there's no C# test suite, by design (see the design doc's Testing section for why).
- **Question wording and thresholds** live only in `brain/jev_vs/questions.py` — keep it that
  way so it stays the one file worth reviewing for prompt changes.
- Match the existing code style in the file you're editing rather than introducing a new one.

## Pull requests

- Describe what you tested it against (a real run, the fake plugin replay, or just the test
  suite) — this project has real physical/API side effects, so "it compiles" isn't much signal
  on its own.
- If you're changing behavior the [Known limitations](README.md#known-limitations) section
  calls out as unverified, please say so and how you verified it.
