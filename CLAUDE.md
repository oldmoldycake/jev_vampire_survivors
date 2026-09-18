# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this is

A BepInEx 5 plugin (`mod/JevSurvivors/`, C#) plus a Python brain (`brain/`) that let TypeSafe's
Jev model play the real Steam build of Vampire Survivors: the plugin streams raw game state over
a local TCP socket and applies whatever the brain answers. Linux only, against a native Mono
build of the game. The plugin holds no strategy — every judgment call lives in the brain, so
nearly all work here is Python.

Setup, ports and tuning knobs: [README.md](README.md). Contribution norms:
[CONTRIBUTING.md](CONTRIBUTING.md). Don't restate them here.

## Commands

Working directory matters: `runs/` and the live tests' fixture lookup are both resolved relative
to it.

From `brain/`:

- `uv run --env-file ../.env jev-vs` — start the brain and dashboard (plugin socket on
  `127.0.0.1:48231`, dashboard on `:48232`). Plain `uv run jev-vs` if the key is already exported.
- `uv run pytest` — the offline suite, under a second.
- `uv run ruff check .` and `uv run ruff format --check .` — the lint contract.
- `uv run pytest -m live` — costs real money; see [Testing](#testing) before you even think about it.

From the repo root:

- `scripts/deploy_mod.sh` — build the plugin and copy the DLL into the game's `BepInEx/plugins/`.
- `uv run --project brain python scripts/fake_plugin.py --replay brain/runs/<stamp>` — replay a
  recorded run into a running brain, no Steam involved. Without a recording:
  `... scripts/fake_plugin.py --ticks 40 --hz 4`.
- `scripts/decompile.sh` — decompile `VampireSurvivors.Runtime.dll` into `decompiled/` to find
  the private member names the plugin hooks.
- `scripts/game_ctl.sh launch|stop|status|log|wait-log PATTERN` — drive the game; needs Steam and
  a GUI session.

The fake plugin walks the whole protocol (hello, character select, stage select, ticks, a
level-up, game over), so it exercises every brain path except the game. Reach for it instead of
asking the human to launch Steam.

## Architecture rules

These are load-bearing. Breaking one tends to look like a reasonable refactor, so check against
this list before restructuring anything.

**Decision logic lives in the brain, never in the plugin.** `mod/` reads state, applies an
answer, and drives menus — that is all it does. It is thin so that changing how Jev decides never
means rebuilding a DLL and restarting Steam. An `if` in a `.cs` file about what makes a *good*
move belongs in `brain/jev_vs/` instead.

**No raw numbers reach the model.** `brain/jev_vs/digest.py` turns a tick into words — compass
sectors (`sector_of`), distance buckets relative to the visible half-height, enemy pressure, gem
counts, HP and XP buckets — and `questions.py` assembles the only two payloads Jev ever sees
(`direction_question`, `options_question`). No coordinate, distance, HP, XP or entity count may
appear in an `Ask.state` or a `Choice.criteria` string; `sector_text` is digit-free and a test
enforces it. The only numerals Jev sees are equipment levels (`WHIP L3`, `would reach level 4`).
`Digest.to_dict()` does carry raw values — it goes to the dashboard and run log, not the model.

**All question wording and every threshold live in `brain/jev_vs/questions.py`.** Instruction
strings, option wording, the `Thresholds` dataclass, the pickup-to-word table. Nothing else in
the repo may hold prompt text or a bucket cut-off. The import direction enforces this: `digest`
imports `Thresholds` from `questions` at runtime, `questions` imports from `digest` only under
`TYPE_CHECKING`, and `protocol` imports `DIRECTION_VECTORS` lazily inside the function. Keep it
one-way.

**The game must never stall waiting on the model.** Both sides have independent deadlines:

- `jev_client.JevClient.ask` raises on any SDK or network error. `decide.Decider._ask` catches
  *everything* (including a well-formed answer that isn't one of the offered keys) and returns
  `None`; the caller substitutes `fallback_direction` (least enemy pressure among unblocked
  sectors, ties to gems) or `fallback_pick` (option 0) and marks the reply `source: "fallback"`.
  Failures warn at most once a minute.
- A tick that arrives while a Jev call is in flight is answered immediately from the last
  direction with `source: "reused"` (`server.PluginServer._on_tick`). Requests never queue.
- Plugin side: a tick gives up after `ReplyTimeoutMs` (400 ms) and keeps the previous vector,
  which `Movement.Expire` zeroes after 1 s of silence; menus give up after `MenuReplyTimeoutMs`
  (3 s) and take option 0. A reply arriving after its deadline has no pending entry left to
  match, so `Transport` forwards it to `Plugin.OnUnsolicited` → `Movement.Apply`: stale brain
  knowledge still beats none. That is intentional — don't "fix" it by dropping late replies.

**Two `BlockMemory` behaviours in `digest.py` look wrong and are not.** A remembered blocked
direction expires on elapsed run time only, never because the survivor moved some other way; and
the position trail keeps twice `stuck_window_s` of samples. Both docstrings explain why, and each
was a real bug fix. Don't simplify either.

## Testing

`uv run pytest` from `brain/` is offline and hermetic (`FakeJev` in `tests/conftest.py`).
`addopts = "-m 'not live'"` deselects the `live` tests by default.

**Never run `pytest -m live` unless the human explicitly asks for it.** Those tests call the real
TypeSafe API with the user's key and are billed per call.

Character and stage picks are *sampled* from Jev's probability distribution
(`Decider._sample_choice`, `SAMPLE_FLOOR`), not taken from its top answer, so they are not
deterministic. Pass a seeded `random.Random` into `Decider` when a test needs a fixed outcome.

There is deliberately no C# test suite: the plugin holds nothing worth unit-testing, and the
Unity and BepInEx types can't be loaded outside the game. A plugin change is verified only by
`scripts/deploy_mod.sh` plus a human launching the game and watching
`<game>/BepInEx/LogOutput.log`. You cannot do that from here — say "reviewed, not verified" about
any `mod/` change rather than implying it works.

## Secrets and logs

- `TYPESAFE_API_KEY` lives in a git-ignored `.env` at the repo root. Never `cat`, `echo`, print,
  log or commit it. Hand it to processes with `uv run --env-file ../.env`; never interpolate it
  into a command line.
- `brain/runs/<timestamp>/` holds `ticks.jsonl`, `events.jsonl` and `summary.json` — full game
  state, the digests sent to Jev, and its answers. Git-ignored; don't commit them and don't paste
  one wholesale into a message. Quote the two lines you need.
- `decompiled/` holds decompiled game code. Git-ignored and must stay that way; it is poncle's
  code, not this project's.

## What can't be verified here

- The game needs Steam and a real GUI session, and there is none in this environment. Anything
  ending in "launch the game and watch" is a request for the human.
- The plugin can't build in CI: `JevSurvivors.csproj` references the shipped game assemblies
  (`VampireSurvivors.Runtime.dll` and friends) through a publicizer, so `dotnet build` only works
  where the game is installed. CI runs the Python suite only.
- The README's Known limitations section lists paths that were code-reviewed but never exercised
  in a live run (treasure chests, a full 30-minute clear, the revive path, the F9 hotkey). Don't
  quietly upgrade one to "works"; if you touch that code, state exactly what you ran.

## Conventions

- Commits follow Conventional Commits with a scope: `feat(brain):`, `fix(mod):`, `test(brain):`,
  `docs:`. Lowercase imperative subject, no trailing period; the only scopes in use are `brain`
  and `mod`. Check `git log --oneline -30` before writing one.
- Python: ruff with `line-length = 120` and `select = ["E", "F", "I", "UP", "B"]`. The code is
  laid out wide on purpose — aligned lookup tables, one-line wire-format dicts.
- Match the surrounding file's style instead of introducing a new one. The brain and the plugin
  are each internally consistent and deliberately unlike each other.
- Comments here explain *why*, often at length, and several record a ruling from a past review.
  Preserve them when editing around them.
