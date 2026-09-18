# Docs

**You don't need anything in here to use this project.** [The README](../README.md) is
self-contained: it covers setup, running, tuning and development. This directory is the paper
trail from the original build, kept in the repo for transparency.

This project was built with a spec-driven workflow: a design doc written and reviewed first,
then a task-by-task plan per component, then a ledger recording how each task actually went.
Those documents are all under `superpowers/`, grouped by what they are.

Three things to keep in mind while reading them:

- **They are historical records, not living documentation.** They describe the project as it
  was designed and built up to version 0.1.0 and are not updated as the code changes. Where a
  document and the code disagree, the code is right.
- **The code is the authority on behavior; these explain the reasoning.** They are the most
  complete answer to "why does it work this way" — why raw numbers never reach the model, why
  the plugin holds no strategy, how the protocol was arrived at — and the starting point if you
  want to port or substantially change any of it.
- **They are verbatim build logs from an AI-assisted workflow**, kept unedited. That means they
  also contain agent bookkeeping — worktree paths, review rulings, commit-trailer conventions —
  which is noise if you came here for the design. Skim past it.

## `superpowers/specs/` — the design

- [`2026-09-17-jev-vampire-survivors-design.md`](superpowers/specs/2026-09-17-jev-vampire-survivors-design.md)
  — the full design: goals, the two-process architecture, the plugin/brain wire protocol, the
  state-digest rules, every question Jev is asked, the dashboard, and the cadence and budget
  math. Section 2 is the verified-facts section: what was confirmed by hand about the TypeSafe
  API and about the decompiled game assembly (class, field and method names the plugin hooks),
  with the evidence for each. That section is the thing to re-check first if a game update
  breaks the plugin.

## `superpowers/plans/` — the task breakdown

- [`2026-09-17-jev-vs-brain.md`](superpowers/plans/2026-09-17-jev-vs-brain.md) — the Python
  brain, broken into ordered tasks: protocol codec and config, the state digest, the questions
  module, the Jev client and decider, run logs, the TCP server, and the dashboard.
- [`2026-09-17-jev-vs-plugin.md`](superpowers/plans/2026-09-17-jev-vs-plugin.md) — the C#
  BepInEx plugin, likewise: scaffold and config, the TCP transport, tick sampling and movement,
  the menu driver, and the run loop. Each task names the files it touches and how it was to be
  verified.

## `superpowers/ledgers/` — what actually happened

- [`2026-09-18-brain-ledger.md`](superpowers/ledgers/2026-09-18-brain-ledger.md) — the
  execution log for the brain plan: the pre-flight conflict scan, a per-task entry with what
  was built and what code review found, and the findings that were deliberately deferred.
- [`2026-09-18-plugin-ledger.md`](superpowers/ledgers/2026-09-18-plugin-ledger.md) — the same
  for the plugin, including the acceptance-run evidence and the deferred findings behind the
  [Known limitations](../README.md#known-limitations) section of the README.

## Elsewhere

- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — how to build, test and send a change.
- [`../CHANGELOG.md`](../CHANGELOG.md) — what changed in each release.
