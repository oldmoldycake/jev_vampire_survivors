# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**Versioning across the two halves.** The Python brain (`brain/pyproject.toml`) and the C#
plugin (`mod/JevSurvivors/JevSurvivors.csproj`) carry the same version number and are released
together as one thing — they speak a private protocol to each other and are not expected to
work across versions. A release bumps both, and one entry below covers both. The version tag
is `vX.Y.Z` on this repository; there is no separate plugin release channel and no package
published to PyPI or to a mod portal.

## [Unreleased]

### Added

- **Pin a character or a stage from the dashboard.** Two dropdowns beside the Pause button
  override Jev's choice for the next run: the pinned pick is applied directly, costs no API
  call, and is marked `human` in the run log and on the decision card. Leaving both on
  "JEV DECIDES" is the default and keeps the previous behaviour exactly. Pins survive a brain
  restart in `brain/pins.json`, and a pin the game does not offer that run falls back to Jev
  with a note in the dashboard log rather than being silently dropped. No plugin change: the
  game never learns a human was involved.

### Fixed

- A human-pinned pick is no longer counted as a Jev fallback in the dashboard's run stats,
  which would have reported an API problem that never happened.

## [0.1.0] - 2026-09-18

First public release. Jev plays Vampire Survivors end to end: from the boot screen to a
character, a stage, every level-up, and the walking direction four times a second, with a live
dashboard showing each decision as it is made.

### Added

- **Autonomous play.** The plugin takes the game from the boot warning through character and
  stage selection into a run, handles level-ups, arcana, treasure chests, unlock popups, pause
  and game over, and then starts the next run — with no human input after Steam launches the
  game. A run budget (`MaxRuns`) and a pause between runs are configurable.
- **Jev makes every decision.** Character, stage, each level-up or arcana pick, and the
  movement direction each tick all come from the model. The brain turns raw game state into
  words first — compass sectors, distance and HP buckets, never raw coordinates — so the model
  reasons about a described situation rather than numbers.
- **All prompt wording in one file.** Every question, option label, instruction and threshold
  lives in `brain/jev_vs/questions.py`, the only file to read or edit to change how Jev is
  asked things.
- **World awareness beyond the nearest enemy.** Ticks carry XP-gem pressure, the current stage
  objective, and which directions are blocked by scenery; blocked directions are remembered for
  a few seconds so the brain can notice when the survivor is shuffling against a wall instead
  of making progress. Character and stage picks are deliberately varied across runs rather than
  converging on one favourite.
- **Safe defaults when the model is not there.** A missing API key, a slow response or a
  dropped connection falls back to a local heuristic and the game keeps playing; the plugin
  never stalls waiting for an answer, and reconnects to the brain on its own. Fallback
  decisions are marked as such in the logs and on the dashboard.
- **Live ops dashboard** at <http://127.0.0.1:48232/>, served by the brain over a WebSocket: a
  card per question with a probability bar per option, the chosen option highlighted,
  confidence, latency, call count and running cost, plus a radar view of what the model was
  shown. It also carries run history, and a Pause control that hands the game back to you
  (as does **F9** in-game).
- **Run logs.** Every run writes `ticks.jsonl`, `events.jsonl` and `summary.json` under
  `brain/runs/<timestamp>/`, with per-run stats including calls made and estimated cost.
- **Replay without the game.** `scripts/fake_plugin.py` replays a recorded run — or synthesizes
  ticks — against a running brain, so the dashboard and the questions can be iterated on
  without launching Steam.
- **Setup and operation scripts:** `scripts/install_bepinex.sh` (installs BepInEx 5 into the
  game folder), `scripts/deploy_mod.sh` (builds the plugin and deploys the DLL),
  `scripts/decompile.sh` (decompiles the game assembly for finding member names), and
  `scripts/game_ctl.sh` (launch, stop, watch the game from a terminal).
- **Test suite** for the brain, offline by default, plus live replay tests against the real
  TypeSafe API behind a `live` marker.
- **Design documents** kept in the repo: the design spec, the implementation plans, and the
  execution ledgers recording what was built, reviewed and deferred — see
  [`docs/README.md`](docs/README.md).

### Fixed

Issues found and closed during the initial build, before this release shipped:

- `scripts/install_bepinex.sh` now pins and verifies the BepInEx archive's SHA-256 before
  unpacking anything into the game folder, instead of trusting the download.
- `scripts/decompile.sh` validates that the game assembly exists before installing a global
  dotnet tool and deleting any previous decompile output.
- `scripts/game_ctl.sh wait-log` with no pattern prints its usage instead of failing with an
  unbound-variable error.
- Corrected the documented replay command, which pointed at a path that could not resolve from
  the directory the README told you to run it in.
- `brain/config.toml` no longer presents `tick_hz` as the tick-rate control; the plugin's
  `TickHz` is the setting that takes effect.
- A revived run is no longer counted twice against the run budget.
- The offline fallback direction now respects blocked directions instead of walking into
  scenery, and the steering instructions given to the model were clarified.
- The "survivor is stuck" check is now reachable with real tick timing rather than only in
  tests.
- Ticks report the direction actually applied and the distance moved, so a decision that the
  game ignored is visible rather than silently assumed to have worked.
- Level-up options report their real levels, a revive is accepted when the game offers one, and
  stage modifiers are explicitly left off.
- Tick payloads are built only for the nearest entities, keeping the message size bounded.
- Only words reach Jev from a level-up build; numeric leakage was removed.
- The brain closes its Jev client at shutdown, tracks and cancels its server handler tasks,
  guards malformed dashboard control frames, bounds the pre-run buffer, and rate-limits
  fallback warnings.
- The plugin re-checks automation state and page state after waiting on the brain, so a pause
  or a page change during a request cannot apply a stale answer.

### Known limitations

Treasure chests, a full 30-minute stage clear, the revive path and the F9 pause toggle were
verified by code review rather than by a live run that happened to exercise them. See
[Known limitations](README.md#known-limitations) in the README for the current list.

[Unreleased]: https://github.com/oldmoldycake/jev_vampire_survivors/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/oldmoldycake/jev_vampire_survivors/releases/tag/v0.1.0
