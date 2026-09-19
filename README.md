# Jev plays Vampire Survivors

[![CI](https://img.shields.io/github/actions/workflow/status/OldMoldyCake/jev_vampire_survivors/ci.yml?branch=main&label=CI)](https://github.com/oldmoldycake/jev_vampire_survivors/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![Platform: Linux](https://img.shields.io/badge/platform-Linux-lightgrey)](#platform-support)

[TypeSafe](https://typesafe.ai/)'s **Jev** model picks the character, the stage, every level-up,
and the walking direction four times a second, in the real Steam game — with a live ops
dashboard showing every decision as it happens.

A BepInEx plugin reads the game's live state and drives its menus and movement; a Python
"brain" turns that state into plain-English questions, asks Jev, and streams the answers to a
browser dashboard. Neither process has any game-specific strategy hard-coded beyond "ask the
model" — see [How it works](#how-it-works) for the full picture, and
[`docs/superpowers/specs/2026-09-17-jev-vampire-survivors-design.md`](docs/superpowers/specs/2026-09-17-jev-vampire-survivors-design.md)
for the original design doc this was built from.

Not affiliated with [poncle](https://poncle.games/) (the developer of Vampire Survivors) or
with TypeSafe. Vampire Survivors is poncle's trademark. This repository contains none of the
game's assets or code — only a small plugin that talks to the game process over local memory
hooks, the same way any other BepInEx mod does.

## Is this for you?

You'll get the most out of this if you have:

- Vampire Survivors on Steam, on **native Linux** (see [Platform support](#platform-support) —
  this does not work on Windows or macOS as shipped).
- Access to TypeSafe's Jev model and an API key. Without a key the brain still runs, but every
  decision falls back to a small heuristic instead of the model (see
  [`.env.example`](.env.example)).
- Some comfort with the command line; setup involves a few scripts and one manual Steam setting.

## How it works

Two local processes, no cloud infrastructure of your own to run:

```
Steam ──launches──▶ Vampire Survivors (Unity, Mono)
                       └─ BepInEx 5 ─▶ JevSurvivors plugin (C#)
                                          │  newline-delimited JSON over TCP 127.0.0.1:48231
                                          ▼
                                   brain (Python, uv, typesafe-sdk)
                                     │                 │  HTTPS
                                     │ HTTP + WebSocket ▼
                                     │          api.typesafe.ai (jev-latest)
                                     ▼
                              browser dashboard (http://127.0.0.1:48232)
```

- **Plugin (`mod/`)** is deliberately thin: it reads raw game state, applies the brain's
  answers, and drives menus. It holds no strategy of its own, so it never needs updating when
  you change how Jev decides things.
- **Brain (`brain/`)** owns all the judgment: turning raw coordinates into words a language
  model can reason about (compass sectors, distance buckets, HP buckets — never raw numbers),
  the question definitions, calling Jev, safe fallbacks when the model or network is
  unavailable, run logs, and the dashboard.
- **Dashboard** is one static page the brain serves over a WebSocket: a card per question with
  a probability bar per option, the chosen option highlighted, confidence, latency, and a radar
  view of what the model was shown.

Character and stage picks are *sampled* from Jev's probability distribution rather than taken
as its single top answer, so consecutive runs vary instead of replaying the same opening;
level-up and direction decisions always take its top choice.

The brain starts first and listens; the plugin connects to it when the game loads and
reconnects automatically if the connection drops. If the brain or the API is unreachable, the
plugin keeps the game running on safe defaults — it never stalls waiting for an answer.

Full protocol, state-digest rules, and every design decision behind this are written up in the
[design doc](docs/superpowers/specs/2026-09-17-jev-vampire-survivors-design.md).

## Platform support

Verified only on native Linux Steam builds of Vampire Survivors (a Mono build, no Proton
prefix). The plugin was built and tested against game version 1.16.107 on Unity 6000.0.62f1.

This will **not** work out of the box on Windows or macOS: the Windows Steam depot ships an
IL2CPP build (a different runtime, needing a different flavor of BepInEx and different
tooling), and no macOS build was investigated. If you want to port it, `scripts/decompile.sh`
is the starting point for finding the equivalent members in your build.

Because the plugin reaches into the game's private fields and methods by name (via
[Harmony](https://harmony.pardeike.net/) patches and a publicizer, not through any public
modding API), a future Vampire Survivors update can rename or remove something this project
depends on and break it. If that happens, `scripts/decompile.sh` re-decompiles the current
game assembly so you can find the new member names and update the matching C# file.

## Requirements

Install once, in any order:

- **Vampire Survivors**, purchased and installed via Steam, with Steam running.
- **`curl`, `unzip` and `sha256sum`**, used by `scripts/install_bepinex.sh` (present on most
  distros already).
- **[uv](https://github.com/astral-sh/uv)** — runs and manages the Python brain. Python 3.12+
  is pulled in by `uv` automatically; you don't need to install Python yourself.
- **.NET 8 SDK**, to build the C# plugin:
  ```bash
  curl -sSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 8.0
  ```
  This installs to `~/.dotnet`; the provided scripts add it to `PATH` for you.
- **A TypeSafe API key** for the Jev model, if you want real decisions instead of the
  fallback heuristic. See [`docs/superpowers/specs/...design.md`](docs/superpowers/specs/2026-09-17-jev-vampire-survivors-design.md#2-facts-this-design-rests-on)
  for the API details, or [docs.typesafe.ai](https://docs.typesafe.ai/) directly.

## One-time setup

Run these from the repository root.

1. **Install BepInEx into the game folder** (safe to re-run):
   ```bash
   scripts/install_bepinex.sh
   ```
   Then, in Steam: right-click Vampire Survivors → Properties → Launch Options, and set it to
   exactly:
   ```
   ./run_bepinex.sh %command%
   ```

2. **Build and deploy the plugin:**
   ```bash
   scripts/deploy_mod.sh
   ```
   This builds `mod/JevSurvivors` and copies the DLL into
   `<game>/BepInEx/plugins/JevSurvivors/`. Re-run this any time you change the C# plugin.

3. **Set your API key.** Either export it in the shell that will run the brain:
   ```bash
   export TYPESAFE_API_KEY=...
   ```
   or copy [`.env.example`](.env.example) to a git-ignored `.env` at the repo root and fill it
   in — the run command below picks it up automatically.

If your Steam library isn't at the default location
(`~/.local/share/Steam/steamapps/common/Vampire Survivors`), pass `GAME_DIR=/path/to/game`
before any of the scripts above, e.g. `GAME_DIR=/mnt/games/... scripts/install_bepinex.sh`.

## Play

```bash
cd brain && uv run --env-file ../.env jev-vs      # or plain `uv run jev-vs` if you exported the key
```

This starts the brain and the dashboard at <http://127.0.0.1:48232/>. Open that in a browser,
then launch Vampire Survivors from Steam and touch nothing: the plugin continues the warning
and landing screens, picks a character and stage through Jev, and plays. A run ends at death
(or a revive, if the game offers one) or when the stage timer runs out; after a short pause,
the next run starts automatically.

A few things worth knowing while it's running:

- **Don't click into the game window** while a run is going. The game pauses when it loses
  focus, and the plugin resumes it — a click while paused can register as a menu press.
- **F9** in the game, or the **Pause** button on the dashboard, hands control back to you
  immediately; press again to resume. Toggling automation off stops Jev calls (and their cost)
  until you turn it back on. If a menu was open when you paused, it needs one manual press from
  you before automation can pick up from there again.
- **Pin a character or a stage** from the dashboard's CHARACTER and STAGE dropdowns and the brain
  applies your choice instead of asking Jev, from the next menu onward — the run in progress is
  not disturbed. Leave them on JEV DECIDES (the default) and nothing changes. A dropdown lists
  what the game last offered, so it fills in the first time a menu opens; a pin the game does not
  offer that run is kept, noted in the dashboard log, and that one pick goes back to Jev.
- Run logs land in `brain/runs/<timestamp>/` (`ticks.jsonl`, `events.jsonl`, `summary.json`) —
  useful for later analysis or for replaying into the brain (see [Develop](#develop)).
- Watch the cost. Jev calls are metered by TypeSafe; the dashboard header and each run's
  `summary.json` show calls made and running cost. At the default 4 Hz tick rate this design
  was budgeted at roughly $0.36/hour — see the design doc's ["Cadence and budget"](docs/superpowers/specs/2026-09-17-jev-vampire-survivors-design.md#cadence-and-budget)
  section for the math, and treat it as an estimate, not a guarantee.

## Tuning

- **Questions and thresholds** (what Jev is asked, and the wording of every option): `brain/jev_vs/questions.py` — the only file this project's prompt wording lives in.
- **Brain ports, model, timeouts:** `brain/config.toml`. The tick rate is *not* set here — the
  plugin drives the cadence, so change `TickHz` in the plugin config below. `state_file` names
  where dashboard pins are remembered (`brain/pins.json` by default, git-ignored).
- **Plugin timing, entity caps, run count, hotkey:** `<game>/BepInEx/config/dev.oldmoldycake.jevsurvivors.cfg` (named by the plugin's GUID, not by its display name — it won't appear as `JevSurvivors.cfg`). Key settings: `AutoplayOnBoot`, `MaxRuns` (0 = unlimited), `PauseBetweenRunsS`, `ToggleKey` (default `F9`), `TickHz`, `MaxEntities`.

## Develop

- **Brain tests:** `cd brain && uv run pytest` (all offline by default; `uv run pytest -m live`
  additionally runs tests that call the real TypeSafe API and need `TYPESAFE_API_KEY`).
- **Replay a run into the brain without the game**, useful for iterating on the dashboard or
  questions without launching Steam:
  ```bash
  # one terminal, from the repository root:
  (cd brain && uv run jev-vs)
  # another terminal, also from the repository root:
  uv run --project brain python scripts/fake_plugin.py --replay brain/runs/<stamp>
  # or, without a recorded run: uv run --project brain python scripts/fake_plugin.py --ticks 40 --hz 4
  ```
- **Read game internals:** `scripts/decompile.sh` decompiles the game's logic assembly into
  `./decompiled` (git-ignored) with [ilspycmd](https://github.com/icsharpcode/ILSpy), for
  finding the private fields and methods the plugin hooks into.
- **Plugin log:** `<game>/BepInEx/LogOutput.log`.
- **Launch, stop, or watch the game from a terminal:**
  ```bash
  scripts/game_ctl.sh launch | wait-log PATTERN [TIMEOUT] | stop | status | log
  ```

## Repository layout

```
brain/                   Python package (uv), typesafe-sdk, pytest
  jev_vs/
    server.py            TCP server, message loop
    digest.py            raw state -> sector/word summaries (never raw numbers to Jev)
    questions.py         all Jev questions and thresholds — the file to read/edit for tuning
    jev_client.py        TypeSafe SDK wrapper: retries, lazy construction, fallback marking
    decide.py            turns a Jev answer (or a failure) into an applied Decision
    pins.py              human-pinned character/stage and the rosters behind the dropdowns
    runlog.py            JSONL run logs
    hub.py, dashboard.py aiohttp app + WebSocket broadcast for the live dashboard
    static/index.html    the dashboard page (inline CSS/JS, no build step)
  tests/
  runs/                  git-ignored run logs
  pins.json              git-ignored dashboard pins (created on first use)
  config.toml            ports, model, timeouts (tick rate lives in the plugin config)
mod/                     C# BepInEx plugin
  JevSurvivors/          Plugin.cs, Transport.cs, StateSampler.cs, Movement.cs, MenuDriver.cs, Patches.cs
  Directory.Build.props  GameDir / BepInExDir / ManagedDir paths; pass GAME_DIR to
                         deploy_mod.sh, or -p:GameDir=... to a bare dotnet build
scripts/
  install_bepinex.sh     downloads and installs BepInEx 5 into the game folder
  deploy_mod.sh          builds the plugin and copies the DLL into BepInEx/plugins/
  decompile.sh           decompiles the game assembly into decompiled/ (git-ignored)
  fake_plugin.py         replays or synthesizes ticks against a running brain
  game_ctl.sh            launch/stop/watch the game from a terminal
docs/
  README.md              index of the documents below
  superpowers/           design spec, implementation plans, and execution ledgers this
                         project was built from (see below)
.github/
  workflows/ci.yml       lint + brain tests on every push and pull request
  ISSUE_TEMPLATE/        bug report and feature request forms
  PULL_REQUEST_TEMPLATE.md
  CODEOWNERS
  dependabot.yml         dependency update schedule
CHANGELOG.md             what changed in each release
CONTRIBUTING.md          how to build, test, and send a change
CODE_OF_CONDUCT.md       ground rules for taking part
SECURITY.md              how to report a vulnerability
CLAUDE.md                repo conventions for AI coding agents
LICENSE                  MIT
.env.example             the environment variables the brain reads
.editorconfig            shared indentation and whitespace settings
.gitattributes           line-ending and diff settings
```

## Known limitations

- **Linux only** — see [Platform support](#platform-support).
- **Treasure chests and a full 30-minute stage clear were verified by code review, not by a
  live run** that happened to encounter them; if you hit an issue there, check
  `mod/JevSurvivors/MenuDriver.cs`'s treasure-page handling first.
- **The revivable-death path** (accepting a revive instead of ending the run) is implemented
  but wasn't exercised in the recorded acceptance run, and there's a known low-severity gap:
  toggling automation off during the ~2-second game-over wait can skip a revive the game
  offered.
- **F9 (manual pause/resume) needs a human** to verify — it wasn't exercised by an automated
  test run.
- Stage modifiers (hyper, hurry, inverse, endless), Adventures mode, and merchant purchases are
  out of scope; Jev only ever picks among what the game already offers.

More detail, including every deferred finding from the original build, is in
[`docs/superpowers/ledgers/`](docs/superpowers/ledgers/).

## Background / design docs

This project was built with a spec-driven workflow, and the documents from that process are
kept in the repo for transparency — [`docs/README.md`](docs/README.md) indexes them:

- [`docs/superpowers/specs/`](docs/superpowers/specs/) — the design doc, including every
  verified fact about the TypeSafe API and the decompiled game assembly it's based on.
- [`docs/superpowers/plans/`](docs/superpowers/plans/) — the implementation task breakdown.
- [`docs/superpowers/ledgers/`](docs/superpowers/ledgers/) — a task-by-task log of what was
  built, reviewed, and deferred.

You don't need to read any of this to use the project — [Play](#play) and
[Develop](#develop) above are self-contained — but it's the most complete answer to "why does
it work this way."

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for how to build, test, and send a change, and
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) for the ground rules. Released versions and what
changed in each are in [`CHANGELOG.md`](CHANGELOG.md).

## Security

Both servers this project starts (the plugin link on port 48231 and the dashboard on 48232)
bind to `127.0.0.1` and are unauthenticated, so anything with an account on the same machine
can drive them; the only secret involved is your TypeSafe API key, which belongs in a
git-ignored `.env` and nowhere else. To report a vulnerability, see
[`SECURITY.md`](SECURITY.md) rather than opening a public issue.

## License

[MIT](LICENSE).
