# Jev plays Vampire Survivors: design

Date: 2026-09-17
Status: approved in brainstorming, pending written review

## 1. Goal

Let TypeSafe's Jev model play the real Vampire Survivors (Steam, native Linux build) with no human input after the game is launched. Jev makes four kinds of decision: which character, which stage, which upgrade at every level-up (arcana prompts included), and which direction to move, several times per second. A run ends at death or when the stage timer ends, the run is logged, and the next run starts.

Success for v1:

- From the main menu, a run starts, plays, and ends with zero human input, then another run starts.
- Every Jev decision is logged with its probabilities, confidence, and latency.
- A browser dashboard shows those decisions as they happen: every question as a card with a probability bar per option, the chosen option highlighted, confidence, latency, call count, and running cost, plus a radar of what the player sees.
- The questions and thresholds live in one reviewable Python module.
- If the brain or the Jev API is unavailable, the game keeps running on safe defaults and never stalls.

## 2. Facts this design rests on

### Jev / TypeSafe

- API: `POST https://api.typesafe.ai/v1/systemone`, bearer auth via `TYPESAFE_API_KEY`. Python SDK `typesafe-sdk` (0.6.0 verified installable, Python >= 3.10) with `TypeSafeClient` / `AsyncTypeSafeClient`, `Choice`, `Score`, `Noul`, `RetryPolicy`.
- One request carries a `state` (string, JSON object, or array of text) and a dict of questions. All questions in one request are evaluated in parallel, so extra questions add no latency.
- `Choice` returns `choice`, `probabilities` (sums to 1), and `confidence`. Up to 255 options. Option descriptions may be strings or structured objects (`what`, `not_for`, `examples`).
- Model ids: `jev-latest` (currently `jev-1.13.0`). Limits: 32k tokens of state per request, 1,200 requests per minute, 250k tokens per second. Latency 70 to 500 ms. Input costs $0.042 per million tokens, output is free.
- Documented weaknesses of jev-1.13: cannot count or do arithmetic, cannot compare numbers reliably, performs worse on numeric than semantic representations, accuracy falls as unrelated state grows, and it reads instructions literally. Consequence: the brain converts all geometry into words before asking.

### The game install

- Path: `~/.local/share/Steam/steamapps/common/Vampire Survivors`. Version 1.16.107 on Unity 6000.0.62f1.
- The Linux build is a native Mono build: `VampireSurvivors.exe` is an ELF executable started by `launcher.sh`; `UnityPlayer.so`, `MonoBleedingEdge/`, and a full `Managed/` folder are present. No Proton prefix exists. The IL2CPP files in the same folder belong to the Windows depot and are not used.
- Game logic is in `VampireSurvivors_Data/Managed/VampireSurvivors.Runtime.dll` (10 MB, not obfuscated). `Assembly-CSharp.dll` holds generated networking code only.
- Input is Rewired. The player controller keeps `_currentDirection`, `_currentDirectionRaw`, and `_lastMovementDirection` fields.
- Classes verified by reading the assembly metadata:
  - `VampireSurvivors.Framework.GM` (static `Core`), `GameManager` (`_stage`, `_levelUpFactory`, `_gameSessionData`, `_playerOptions`, `_dataManager`, `AddStartingWeapon`, `RestartGameScene`), `EnemiesManager`, `LevelUpFactory` (`GetLevelUpItems`, `GetLevelUpOptions`), `WeaponsFacade`, `Loot.LootManager`.
  - `VampireSurvivors.Objects.Characters.CharacterController` (`_currentHp`, `_level`, `_xp`, `_currentDirectionRaw`, `_currentDirection`, `_weaponsManager`, `_playerStats`, `CurrentHealth`, `ForceSetPosition`), `Objects.Characters.Enemies.EnemyController`.
  - `VampireSurvivors.Objects.Stage` (`GetAllEnemiesInScreenBounds`, `GetAllGemsInScreenBounds`, `GetAllPickupsInScreenBounds`, `GetClosestEnemiesSorted`, `FindClosestEnemy`, `_currentMinute`, `_spawnedEnemies`), `Objects.Pickups.PickupManager`, `Objects.Items.Gem`.
  - `VampireSurvivors.Data.DataManager`.
  - UI pages: `UI.MainMenuPage` (`ShowCharacterSelect`, `_StartButton`), `UI.CharacterSelectionPage` (`_characterItemUIs`, `SelectCharacter`, `ForceSelectCharacter`, `ConfirmCharacter`, `StartButton`), `UI.StageSelectPage` (`GetAvailableStages`, `SelectStage`, `ConfirmStage`), `WeaponSelectionPage`, `UI.ArcanaMainSelectionPage` (`_SkipButton`, `_RandomButton`), `UI.LevelUpPage` (`_spawnedItems`, `SelectWeapon`, `SelectItem`, `Skip`, `Reroll`, `OnLevelUpPageIntroAnimComplete`, `get_LevelUpItems`), `LevelUpItemUI` (`_data`, `_itemData`, `_type`, `Select`, `IsWeapon`, `IsPowerUp`, `IsNew`), `UI.OpenTreasurePage`, `UI.ItemFoundPage`, `UI.CharacterFoundPage`, `UI.GameOverPage` (`Quit`, `OnShowStart`), `UI.RecapPage`, `UI.LandingScreenPage`, `SaveSlotsPage`, `UI.BaseUIPage`.
- Community modding for this game targets the Windows IL2CPP build with MelonLoader. Nothing published targets the Linux Mono build, so this project decompiles the assembly itself with ilspycmd to confirm method bodies.

## 3. Architecture

Two processes on one machine.

```
Steam ──launches──▶ Vampire Survivors (Unity Mono)
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

**Plugin (`mod/`)** is thin on purpose: read raw state, apply actions, drive menus, keep the game alive when the brain is silent. It contains no strategy.

**Brain (`brain/`)** owns everything that needs judgment or iteration: digesting raw state into words, the question definitions, calling Jev, fallbacks, run logs, and the live dashboard. It can be restarted or edited without touching the game.

**Dashboard** is a single static page served by the brain and fed over a WebSocket. It has no logic of its own beyond rendering what the brain broadcasts.

The brain is the TCP server and starts first. The plugin connects on load and reconnects every two seconds after any drop.

## 4. Protocol

One JSON object per line, UTF-8. Every plugin message that expects an answer carries an integer `id`; the brain echoes it. The plugin waits at most `reply_timeout_ms` (default 400 for ticks, 3000 for menu events) then applies the safe default described in section 8.

### Plugin to brain

```json
{"type": "hello", "game_version": "1.16.107", "plugin_version": "0.1.0"}

{"id": 17, "type": "tick", "t": 123.4,
 "state": {
   "player": {"x": 0.0, "y": 0.0, "hp": 71, "max_hp": 120, "level": 9, "xp": 40, "xp_to_next": 85,
              "minute": 6, "seconds": 391, "character": "ANTONIO",
              "weapons": [{"id": "WHIP", "level": 4}], "passives": [{"id": "SPINACH", "level": 2}]},
   "enemies": [{"x": 3.1, "y": -0.4, "hp": 12, "type": "BAT", "boss": false}],
   "gems": [{"x": -1.2, "y": 2.0, "value": 1}],
   "pickups": [{"x": 5.0, "y": 5.0, "kind": "CHEST"}],
   "screen": {"half_w": 8.0, "half_h": 4.5}
 }}

{"id": 18, "type": "event", "event": "character_select",
 "options": [{"id": "ANTONIO", "name": "Antonio Belpaese", "description": "Gains 10% more damage every 10 levels. Starts with Whip."}]}

{"id": 19, "type": "event", "event": "stage_select",
 "options": [{"id": "FOREST", "name": "Mad Forest", "description": "The Castle is a lie..."}]}

{"id": 20, "type": "event", "event": "level_up",
 "options": [{"index": 0, "id": "WHIP", "name": "Whip", "kind": "weapon", "level": 5, "is_new": false, "description": "Attacks horizontally, passes through enemies."}],
 "build": {"weapons": [...], "passives": [...], "level": 9, "minute": 6}}

{"id": 21, "type": "event", "event": "arcana_select", "options": [{"index": 0, "id": "XV", "name": "Disco of Gold", "description": "..."}]}

{"id": 23, "type": "event", "event": "weapon_select",
 "options": [{"index": 0, "id": "WHIP", "name": "Whip", "kind": "weapon", "level": 1, "is_new": true, "description": "..."}]}

{"id": 22, "type": "event", "event": "game_over",
 "summary": {"character": "ANTONIO", "stage": "FOREST", "seconds": 1043, "level": 27, "kills": 1834, "stage_complete": false}}
```

Enemies, gems, and pickups are those the game reports in screen bounds, sorted by distance to the player, capped at `max_entities` (default 200 each). Positions are Unity world units relative to the player, and `screen` gives the half extents of the visible area in the same units so the brain can bucket distances relative to what is on screen. `t` is seconds since the run started.

`level_up` and `weapon_select` options share one shape. The plugin sets `evolution_ready: true` on a weapon option when every entry in that weapon's `WeaponData.evoSynergy` list is already among the player's active weapons or passives (the game's own `LevelUpFactory.HasEvolutionRequirements` is private and judges the evolved weapon, not the offered one, so the plugin does this small check itself); the brain only phrases that flag, it never computes it.

### Brain to plugin

```json
{"id": 17, "type": "move", "dx": 0.0, "dy": 1.0, "choice": "north",
 "probabilities": {"north": 0.41, "north_east": 0.2, "...": 0.0}, "confidence": 0.37, "source": "jev"}

{"id": 20, "type": "pick", "index": 1, "choice": "SPINACH", "probabilities": {"...": 0.0}, "confidence": 0.7, "source": "jev"}

{"id": 22, "type": "noop"}

{"type": "control", "automation": false}
```

`source` is `jev` or `fallback` so logs show which decisions came from the model. `control` has no id and is sent when the dashboard's pause or resume button is pressed; the plugin treats it exactly like the F9 hotkey.

## 5. Brain

### State digest

The brain never forwards raw coordinates to Jev. Per tick it:

1. Assigns each enemy, gem, and pickup to one of eight compass sectors by the angle from the player (45 degrees each, centred on N, NE, E, SE, S, SW, W, NW).
2. Buckets each entity's distance relative to `screen.half_h`: `touching` (< 0.15), `close` (< 0.4), `mid` (< 0.8), `far` (the rest). Thresholds are config values.
3. Computes per sector: enemy pressure (`none`, `light`, `moderate`, `heavy`) from a distance-weighted count, nearest enemy bucket, gem count bucket (`none`, `few`, `many`), and flags for `boss` and `chest`.
4. Buckets player HP (`critical` < 25%, `low` < 50%, `ok` < 90%, `full`).

The exact bucket thresholds are constants in `brain/jev_vs/questions.py` next to the questions they feed.

### Questions (all in `brain/jev_vs/questions.py`)

- **direction** (per tick): `Choice` with nine options, `north` ... `north_west` plus `stay`. Each option's description is that sector's summary in words, for example "heavy enemy pressure, nearest touching, no gems". State is a JSON object with the player summary. Instructions tell Jev to move away from heavy pressure and toward gems, to prefer safety when HP is low or critical, and to prefer gems when HP is ok or full.
- **level_up** (per level-up, weapon-select, or arcana prompt): `Choice` over the offered options, description carrying name, kind, level it would reach, whether it is new, whether `evolution_ready` is set, and the in-game text. State is the current build. Instructions ask for the option that most strengthens the current build.
- **character** (per run): `Choice` over unlocked characters with in-game descriptions.
- **stage** (per run): `Choice` over unlocked stages with in-game descriptions.

Every answer is applied by code: the direction name maps to a unit vector, the pick maps to an option index. Jev never sees or produces numbers it has to reason about.

### Cadence and budget

- Ticks arrive at `tick_hz` (default 4). The brain answers each tick with one Jev request. If a request is still in flight when the next tick arrives, the new tick is dropped and the in-flight answer is reused; this keeps the plugin at the latest decision rather than a queue of stale ones.
- Budget at 4 Hz with roughly 600 input tokens per tick: about 2,400 tokens per second and 14,400 requests per hour, well under the 250k tokens per second and 1,200 requests per minute limits, at roughly $0.36 per hour.

### Fallbacks

- Jev request fails or times out after the SDK retry policy: direction falls back to the sector with the least pressure that also has the most gems (a tiny heuristic), and picks fall back to option index 0. The reply is marked `source: fallback`.
- Brain cannot reach the API at all: it keeps answering with the fallback and logs once per minute.

## 6. Plugin

BepInEx 5.4.23.5 plugin, C#, HarmonyX patches. Private game fields are reached through `BepInEx.AssemblyPublicizer.MSBuild` on `VampireSurvivors.Runtime.dll` so the code reads like normal C#. Target framework is decided by the spike in section 10 (`netstandard2.1` expected).

Responsibilities:

- **Transport**: background thread owning the TCP connection, reconnecting on failure. Outgoing messages are queued from the Unity main thread; incoming replies are stored and consumed on the main thread. No Unity API is touched off the main thread.
- **Tick sampler**: a MonoBehaviour that every `1 / tick_hz` seconds, while a run is active and automation is on, builds the tick state from `GM.Core`, its `Stage`, and the player `CharacterController`, and sends it.
- **Movement**: a Harmony postfix on the player controller's per-frame input read overwrites `_currentDirectionRaw` and `_currentDirection` with the latest `move` vector while automation is on. The exact method is confirmed by decompilation in the first implementation task.
- **Menu driver**: Harmony postfixes on `Start` of `LandingScreenPage` and on `OnShowStart` of `MainMenuPage`, `CharacterSelectionPage`, `WeaponSelectionPage`, `StageSelectPage`, `ArcanaMainSelectionPage`, `LevelUpPage` (after its intro animation completes), `OpenTreasurePage`, `ItemFoundPage`, `CharacterFoundPage`, `GameOverPage`, and `RecapPage`. Each waits a short configurable delay for the page to finish populating, gathers its options, sends the event, and applies the reply through the page's own methods (`ForceSelectCharacter` and `ConfirmCharacter`, `SelectStage` and `ConfirmStage`, the level-up item's `Select`, `Quit`, or the page's default confirm).
- **Safety net**: any `BaseUIPage` subclass without a specific handler that stays open longer than `unknown_page_timeout_s` (default 10) gets its default confirm invoked, and the incident is logged.
- **Kill switch**: F9 or a `control` message from the brain toggles automation. When off, movement and menu hooks do nothing and the human plays; ticks are still sent so the brain keeps logging and the dashboard keeps drawing.
- **Config** (`BepInEx/config/JevSurvivors.cfg`): host, port, tick_hz, reply timeouts, max_entities, hotkey, autoplay_on_boot, max_runs (0 = unlimited), pause_between_runs_s.

## 7. Run loop

1. Game boots. The landing page ("press any key") is continued.
2. Main menu shows. Plugin calls `ShowCharacterSelect`.
3. Character select shows. Plugin sends the unlocked list, applies the pick, confirms. If a weapon selection page appears, the plugin sends a `weapon_select` event, which the brain answers with the level-up question.
4. Stage select shows. Plugin sends available stages, applies the pick, confirms with default modifiers (no hyper, hurry, inverse, or endless).
5. Run starts. Ticks flow; movement follows Jev. Level-up and arcana pages are answered. Treasure and unlock pages are dismissed.
6. Game over shows. Plugin sends the summary, quits to the recap, confirms, and returns to the main menu.
7. After `pause_between_runs_s`, step 2 repeats until `max_runs` is reached.

## 8. Failure handling

| Situation | Plugin behaviour | Brain behaviour |
|---|---|---|
| Brain not running or connection drops | Keeps the last movement vector for up to 1 s, then stops moving; menus wait `reply_timeout_ms` then take option 0 or default confirm; reconnects every 2 s | n/a |
| Tick reply late | Ignored if a newer reply exists; otherwise applied when it arrives | Drops overlapping ticks |
| Jev error or timeout | Applies whatever reply arrives | SDK `RetryPolicy` then heuristic fallback, reply marked `fallback` |
| Unknown UI page | Default confirm after `unknown_page_timeout_s`, logged | n/a |
| Exception inside a Harmony patch | Caught and logged; the original game method still runs | n/a |
| Human presses F9 | Automation off, game is playable by hand | Keeps logging |

The guiding rule: the plugin must never leave the game frozen on a screen, and a bug in the brain must never crash the game.

## 9. Logging and configuration

The brain writes `runs/<YYYYMMDD-HHMMSS>/`:

- `ticks.jsonl`: one line per tick with the raw state, the digest sent to Jev, the answer, probabilities, confidence, source, and latency.
- `events.jsonl`: every menu event and its answer, same fields.
- `summary.json`: character, stage, seconds survived, level, kills, counts of jev versus fallback decisions, mean latency.

The brain reads `brain/config.toml` (plugin port, dashboard port, tick_hz, model, request timeout, retry policy, digest thresholds, log directory). The plugin reads its BepInEx config file.

## 10. Dashboard

Modelled on TypeSafe's Doom demo: a dark "ops" page beside the game window, refreshed live, never polled.

**Serving.** The brain runs an `aiohttp` app on `127.0.0.1:48232` (configurable). `GET /` returns one static HTML file with inline CSS and JavaScript, no build step. `GET /ws` upgrades to a WebSocket. Each browser client receives a `snapshot` message on connect (current run, latest decision per question, stats) and then a stream of `decision`, `tick`, `event`, `stats`, and `run` messages. The brain publishes to an in-process broadcast after every Jev answer, every fallback, every menu event, and every run start or end; tick digests are broadcast at most at `tick_hz`. A slow client is dropped rather than allowed to back up the brain.

**Panels.**

- Header: run id, character and stage, plugin and Jev connection status, calls this run, last and average latency, cost this run and projected cost per hour, jev versus fallback counts, and a pause/resume button that sends the `control` message.
- Judgments column: one card per question kind (`direction`, `level_up`, `character`, `stage`), each showing the instructions text, a horizontal bar per option labelled with its probability, the chosen option highlighted, the confidence value, latency, and source. The direction card updates every tick; the others hold their last answer until the next event.
- Radar: a canvas with the player at the centre, the eight sectors shaded by pressure level, enemies, gems, chests, and bosses as dots at their relative positions scaled to the screen extents, and an arrow for the chosen direction. Drawn from the same digest and raw entities the brain used, so what the viewer sees is what Jev was told.
- Status strip: HP bucket and value, level, minute, current weapons and passives.
- Log: the last 50 events (level-ups, picks, fallbacks, page dismissals) and a table of previous run summaries from this session.

**Out of v1.** Embedding the live game video in the page. The game window sits beside the browser. Wayland screen capture into a browser stream is a separate pipeline and is listed as a stretch item in section 13.

## 11. Testing

**Spike first (blocking everything else).** Install BepInEx 5.4.23.5 Linux x64 into the game folder, set the Steam launch option `./run_bepinex.sh %command%`, boot the game, and confirm the BepInEx console shows the Unity 6 Mono runtime loaded. Then build a hello-world plugin with one Harmony postfix that logs the player's position each second during a run. This settles the target framework, publicizer setup, and whether BepInEx 5 is viable on this Unity version; if it is not, the fallback is BepInEx 6 pre-release (UnityMono) and the rest of the design is unchanged.

**Brain (pytest, all offline unless marked).**

- Unit tests for the sector digest: known entity layouts produce the expected sector labels, distance buckets, pressure levels, and HP buckets.
- Unit tests for answer application: every direction name maps to the right unit vector; picks map to indices; malformed answers fall back.
- Protocol tests: a fake plugin client (`scripts/fake_plugin.py`, also usable by hand) sends recorded ticks and events over TCP and asserts the reply shape, id echoing, and timeouts, with the Jev client mocked.
- Live replay tests marked `live`: feed recorded ticks from `runs/` to the real API and assert the responses are well-formed and within latency budget. Skipped unless `TYPESAFE_API_KEY` is set and `-m live` is passed.
- Dashboard tests: `GET /` serves the page, a WebSocket client receives a `snapshot` on connect and a `decision` message after the brain records an answer, a pause click produces a `control` message to the fake plugin, and a stalled client is dropped without delaying decisions.
- Visual check: run `scripts/fake_plugin.py` against a recorded run with Jev mocked and confirm the cards, bars, and radar animate in the browser.

**Plugin.**

- `dotnet build` succeeds and `scripts/deploy_mod.sh` copies the DLL into `BepInEx/plugins/JevSurvivors/`.
- Smoke: launch the game with the brain running, confirm `hello`, ticks, and at least one menu event appear in both logs, and that a run starts hands-off.
- Manual: watch one full run; confirm F9 hands control back and forth.

Unity code is not unit tested; that is why the plugin holds no logic worth testing.

## 12. Repository layout and tooling

```
jev_vampire_survivors/
  brain/                 Python package (uv), typesafe-sdk, pytest
    jev_vs/
      server.py          TCP server, message loop
      digest.py          raw state -> sector summaries
      questions.py       all Jev questions and thresholds (the file humans review)
      jev_client.py      TypeSafe SDK wrapper, retries, fallback marking
      runlog.py          JSONL writers
      dashboard.py       aiohttp app, WebSocket broadcast, stats
      static/index.html  the dashboard page (inline CSS and JS)
    tests/
    config.toml
  mod/                   C# BepInEx plugin
    JevSurvivors/        .csproj, Plugin.cs, Transport.cs, TickSampler.cs, Movement.cs, MenuDriver.cs, Config.cs
    Directory.Build.props  GameDir pointing at the Managed folder
  scripts/
    install_bepinex.sh   downloads and extracts BepInEx into the game folder
    deploy_mod.sh        builds and copies the plugin DLL
    decompile.sh         ilspycmd VampireSurvivors.Runtime.dll into decompiled/ (git-ignored)
    fake_plugin.py       replays a run log to the brain
  runs/                  git-ignored run logs
  docs/superpowers/specs/, docs/superpowers/plans/
```

Prerequisites the user installs or sets:

- `sudo pacman -S dotnet-sdk` (builds the plugin and runs `dotnet tool install -g ilspycmd`).
- BepInEx 5.4.23.5 Linux x64 in the game folder and the Steam launch option above (scripted where possible).
- `TYPESAFE_API_KEY` exported in the shell that runs the brain.
- `uv` is already installed; Python 3.14 is present.

## 13. Out of scope for v1

In-game overlay drawn by the mod, live game video embedded in the dashboard (stretch: a Wayland PipeWire capture piped by ffmpeg to an MJPEG endpoint on the brain), co-op and online modes, adventures mode, merchant purchases, reroll/skip/banish strategy at level-up (Jev only picks among the offered items), evolution planning beyond what the option descriptions convey, stage modifiers (hyper, hurry, inverse, endless), and any tick rate above 4 Hz.

## 14. Items resolved during implementation

These depend on reading decompiled method bodies and are settled in the first implementation task, not in this spec:

- The exact per-frame method on `CharacterController` that reads Rewired input, to place the movement postfix.
- Resolved 2026-09-17 by decompiling `VampireSurvivors.Runtime.dll` (see the plugin plan): movement is a Harmony prefix on `CharacterController.ProcessRawDirection`; level-up items are read from `LevelUpPage.LevelUpItems` after `EnableLevelupOptions` and applied with `LevelUpItemUI.Select()`; character select uses `ShowCharacterInfo` then `SelectCharacter(false)` then `ConfirmCharacter()`; stage select uses `SetInfoPanel` then `SelectStage()` then `ConfirmStage()`; the landing page is a plain `MonoBehaviour` whose `MoveToNextView()` continues; `SaveSlotsPage` is a menu-reachable manager, not a boot step; the generic confirm is `BaseUIPage.OnEnterPressed()`.
- Still open, decided by the spike: the plugin target framework (`netstandard2.1` expected, `net472` fallback) and whether BepInEx 5 boots this Unity 6 build.

## 15. References

- TypeSafe docs: quickstart, primitives/choice, concepts/state, models, patterns/fan-out, primitives/advanced, model-jaggedness/jev-1.13, sdk/python/usage (https://docs.typesafe.ai/).
- TypeSafe launch post: https://typesafe.ai/blog/introducing-system-one-models-and-jev
- Coverage: https://www.heise.de/en/news/AI-model-Jev-to-make-machines-decide-faster-11457071.html, https://www.theregister.com/ai-and-ml/2026/09/16/typesafe-ai-debuts-model-for-machines-that-plays-doom/, https://www.latent.space/p/ainews-jev-a-system-one-model-that
- BepInEx releases and Steam interop: https://github.com/BepInEx/BepInEx/releases, https://docs.bepinex.dev/articles/advanced/steam_interop.html
- Community modding reference (IL2CPP, Windows): https://github.com/lukeod/vampiresurvivors-modding, https://gist.github.com/nwfistere/8d325022187395be70d2a81e04c4ff46
