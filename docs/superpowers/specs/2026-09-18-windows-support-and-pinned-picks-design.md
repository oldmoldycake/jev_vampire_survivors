# Windows support and human-pinned character/stage: design

Date: 2026-09-18
Status: proposed

Two independent features, planned together because they were asked for together. They share no
code and ship separately; Part A is small and lands first, Part B is a port with a spike in front
of it.

## 1. Goals

**Part A — pinned picks.** A human can say "play Antonio on Mad Forest" and have the brain honour
it instead of asking Jev, from the dashboard, without restarting anything and without touching the
plugin. Leaving both unset is the default and keeps today's behaviour exactly.

**Part B — Windows support.** A Windows user can install, build, deploy and run the whole project
against the Windows Steam build of Vampire Survivors, following the same README shape a Linux user
follows. The Linux path keeps working unchanged.

Non-goals for both: macOS; Proton-as-a-supported-platform for end users (Proton is a development
verification tool here, not a shipping target); any change to what Jev is asked or how state is
digested.

## 2. Facts this design rests on

Everything in this section was checked on 2026-09-18 against this machine and this repository,
except where marked **unverified**.

### The game install is two builds in one folder

- `~/.local/share/Steam/steamapps/common/Vampire Survivors` holds the Linux Mono build
  (`VampireSurvivors.exe` is an ELF, plus `VampireSurvivors_Data/Managed/` and `MonoBleedingEdge/`)
  **and** the Windows IL2CPP payload: `GameAssembly.dll` and `UnityPlayer.dll` are PE32+, and
  `VampireSurvivors_Data/il2cpp_data/Metadata/global-metadata.dat` is present.
- **Correction, 2026-09-18 22:00:** this stopped being true during Phase 0 preparation.
  **Observed:** `VampireSurvivors.exe` in this folder is now a PE32+ Windows binary with mtime
  2026-09-18 21:03; `VampireSurvivors_Data/Managed/` and `MonoBleedingEdge/` are gone;
  `GameAssembly.dll` is unchanged since 2026-09-11; and `appmanifest_1794680.acf` carries no
  `platform_override` keys with `LastUpdated` 2026-09-11, so the Steam client did not do it.
  **Most likely cause, not observed:** a steamcmd run with `+@sSteamCmdForcePlatformType windows`
  whose `force_install_dir` still pointed at the Steam library, which would rewrite only the
  differing files (the 672K exe) and prune the Mono-only directories, leaving the already-matching
  Windows payload alone. Restoration is pending; see
  `docs/superpowers/plans/2026-09-18-linux-install-recovery.md`. The design conclusion the
  bullet supports still holds: both builds' files can coexist, and the IL2CPP inputs needed for
  interop generation are present without downloading a depot.
- The Windows player is therefore IL2CPP, confirming what README's Platform support section claims.
  The Windows `VampireSurvivors.exe` is not on disk — the ELF of the same name occupies it. **Superseded 2026-09-18 22:00 — see the correction at the end of this group.**
- `steam_appid.txt` is `1794680`.
- Consequence: interop assemblies for the Windows build can be generated on this machine today,
  before any Windows depot is downloaded, because `GameAssembly.dll` and `global-metadata.dat` are
  already here. This is the IL2CPP equivalent of what `decompile.sh` does for Mono.

### This machine can plausibly run the Windows build

- Proton Experimental, 9.0, 10.0, 11.0 and Hotfix are installed under `steamapps/common`.
- `steamcmd` is not installed. Downloading the Windows depot separately needs it (or an equivalent),
  plus an interactive Steam login — **a human step; it cannot be automated from a coding session.** **Superseded 2026-09-18 — steamcmd was installed from the AUR (it is not in the Arch repos) and the Windows depot now exists at `~/games/vs-windows`.**
- **Unverified:** that the Windows build boots under Proton at all, that Steam API init succeeds
  outside the Steam client, and that BepInEx 6's `winhttp` doorstop loads under Proton. Phase 0
  exists to answer exactly these.

### The brain is nearly portable, with one hard blocker

- `brain/jev_vs/__main__.py:57` calls `loop.add_signal_handler(...)`, which raises
  `NotImplementedError` on Windows' event loop. This is the only outright crash found.
- `runlog.py:35` stamps run directories `%Y%m%d-%H%M%S` — no colons, already a legal Windows path.
- Everything else in `brain/` is `pathlib`, `asyncio` and `aiohttp`, all cross-platform.
- CI (`.github/workflows/ci.yml`) runs `ubuntu-latest` only. `.github/workflows/shellcheck.yml`
  exists solely to statically check `scripts/*.sh`.

### BepInEx 6 IL2CPP API

From docs.bepinex.dev v6.0.0-pre.1 (retrieved 2026-09-18):

- Plugins inherit `BasePlugin` and override `Load()`, rather than `BaseUnityPlugin` + `Awake()`.
- `MonoBehaviourExtensions.StartCoroutine(this MonoBehaviour, IEnumerator)` starts a managed
  `IEnumerator` as a game coroutine — the plugin's five coroutines need this extension, not a
  hand-rolled `WrapToIl2Cpp`.
- `IL2CPPChainloader.AddUnityComponent<T>()` registers an injected component with the IL2CPP type
  system and adds it to BepInEx's manager object.
- **Unverified:** the exact BepInEx 6 build to pin and therefore the namespace (`BepInEx.IL2CPP` in
  pre.1 versus `BepInEx.Unity.IL2CPP` in later bleeding-edge builds). Phase 0 pins both.

### What the existing plugin does that will not survive as-is

- `JevSurvivors.csproj` references `VampireSurvivors.Runtime.dll` with
  `BepInEx.AssemblyPublicizer.MSBuild` to reach private members. Under IL2CPP the publicizer is
  unnecessary: Il2CppInterop emits private fields as accessible members. The reference itself is
  replaced by generated interop assemblies.
- `Transport.cs` uses the game's `Newtonsoft.Json` from `Managed/`. Under IL2CPP the game's copy is
  an IL2CPP type and unusable from managed code; the IL2CPP plugin takes Newtonsoft.Json 13.x from
  NuGet and deploys it beside the plugin DLL.
- `TargetFramework` moves `netstandard2.1` -> `net6.0` for the IL2CPP flavour; BepInEx 6 IL2CPP
  hosts CoreCLR.
- `BepInEx.Configuration` is unchanged between 5 and 6, so every `Plugin.*` config entry carries
  over, as does the config file name (`dev.oldmoldycake.jevsurvivors.cfg`).

---

## 3. Part A — pinned character and stage

### 3.1 Shape

No `mod/` changes. Pinning is a decision, and decisions live in the brain (CLAUDE.md architecture
rule). The plugin keeps sending the same `character_select` / `stage_select` events and applying
the same `pick` reply; it never learns that a human was involved.

No `questions.py` changes either. Pinning removes a question rather than adding wording or a
threshold, so the "all prompt text in one file" rule is untouched.

### 3.2 New module: `brain/jev_vs/pins.py`

A `PinStore` holding:

- `character: str | None` and `stage: str | None` — game enum ids such as `ANTONIO`, `MAD_FOREST`.
- `rosters: dict[str, list[dict]]` — the last option list seen per kind, as `{id, name}` pairs.

Persisted as one JSON file so both a pin and the dropdown contents survive a brain restart. The
path comes from one new `config.toml` key, `[brain] state_file = "pins.json"`, resolved relative to
the working directory exactly as `log_dir` already is. Load failures (missing, corrupt, unreadable)
degrade to an empty store and a warning — a bad state file must never stop the brain from playing.

The roster cache exists because the brain only learns which characters are unlocked when a menu
opens. Without it the dashboard's dropdowns would be empty until the first run of the session.

### 3.3 Flow, in `server.py::_on_event`

1. On `character_select` / `stage_select`, record `options` into the roster cache and broadcast
   `{"type": "roster", "kind": ..., "options": [...]}` over the hub so open dashboards repopulate.
2. Resolve the pin for that kind:
   - set and present in `options` -> pass its index down as `pinned_index`;
   - set and absent -> `_note("pinned <id> not offered; asked Jev")`, which surfaces in the
     dashboard event log, and continue down the normal path with the pin left intact (a character
     you are about to unlock stays pinned);
   - unset -> unchanged behaviour.
3. `Decider.pick` gains `pinned_index: int | None = None`. When set it still builds the `Ask` —
   that is pure, does no I/O, and the dashboard card needs its `labels` — then skips `_ask`
   entirely and returns `Decision(kind=..., choice=ask.keys[i], index=i, probabilities={key: 1.0},
   confidence=1.0, latency_ms=0.0, source="human", input_tokens=0)`. No TypeSafe call: no cost, no
   menu latency, and variety sampling and `recently_played` are bypassed by construction.
4. Downstream is unchanged. A pinned pick is an ordinary `Decision`, so the run log, `current_run`,
   the dashboard card and the plugin reply all work as they do today.

`Decider.pick`'s contract is "this index is offered, use it". Deciding whether a pin is honourable
stays in `server.py`, which is where the warning belongs and where the options already are.

### 3.4 `stats.py` needs a third branch

`Stats.record()` is currently `if d.source == "jev": ... else: fallback_calls += 1; jev_ok = False`.
A `"human"` decision would be counted as a fallback and would flip the dashboard's health
indicator, reporting an API problem that did not happen. `record()` gains an explicit branch that
counts the call and touches neither counter, and `snapshot()` is unchanged.

### 3.5 Dashboard

Two `<select>` elements beside the PAUSE button, labelled CHARACTER and STAGE, each with a first
entry "JEV DECIDES" (value empty) followed by the cached roster. They are populated from the WS
snapshot and updated by `roster` messages.

Changing one sends `{"type": "pin", "kind": "character", "id": "ANTONIO" | null}` on the existing
socket. `dashboard.py` routes it exactly as it routes `control` today, to `server.set_pin()`, which
persists and re-broadcasts the new pin so multiple tabs agree. Same channel, same trust model, and
no new attack surface: the socket is loopback and unauthenticated already, and a pin is strictly
less powerful than the pause button.

Pins apply from the next menu onward. A pin changed mid-run does not disturb the run in progress —
there is nothing to disturb, since the character and stage questions are asked once, before it.

### 3.6 Testing

All offline, with `FakeJev` asserting call counts:

- pin honoured -> correct index applied, `source == "human"`, zero Jev calls;
- pin set but not offered -> Jev asked, warning present in the event log, pin still set afterwards;
- roster cache records options and rebroadcasts them;
- pin and roster round-trip through the state file; a corrupt state file yields an empty store;
- `Stats.record` on a human decision leaves `jev_calls`, `fallback_calls` and `jev_ok` alone;
- a `pin` message over the dashboard WebSocket reaches the store.

---

## 4. Part B — Windows support

### 4.1 Shape

Three separable pieces, in order: a spike that answers whether the port is verifiable at all; a
cross-platform rewrite of the helper scripts; the IL2CPP plugin itself, plus the small brain, CI
and documentation changes that make Windows a first-class platform in the repo.

### 4.2 Phase 0 — spike (throwaway)

Exit criteria, in order. Each one that fails stops the phase and gets reported rather than worked
around:

1. **A separate Windows copy of the game exists**, downloaded with
   `steamcmd +@sSteamCmdForcePlatformType windows +force_install_dir <dir> +app_update 1794680`.
   It must be a separate directory: the existing Linux install is the verified, working one and is
   never switched to the Windows depot. Requires an interactive Steam login, so this step is run by
   the human, not by an agent.
2. **The Windows build boots under Proton** and reaches the main menu.
3. **BepInEx 6 IL2CPP loads under Proton** — `WINEDLLOVERRIDES="winhttp=n,b"`, `LogOutput.log`
   written, interop assemblies generated into `BepInEx/interop/`.
4. **A hello-world `BasePlugin` loads and logs.**
5. **The members the plugin needs survive in the interop assemblies** — at minimum
   `CharacterSelectionPage._characterItemUIs`, `StageSelectPage._spawned`, `LevelUpPage._spawnedItems`,
   `CharacterController._currentDirectionRaw`, `Stage.GetAllEnemiesInScreenBounds` — recorded as a
   list of what is present, renamed or missing.

**Decision point at the end of Phase 0.** The chosen structure is shared source plus per-project
`global using` alias files and a small number of `#if IL2CPP` blocks. If step 5 shows the type
surface diverging past what aliases can absorb — different member names, different shapes, not just
different namespaces — the fallback is two independent sibling projects with deliberate
duplication. The criterion is recorded here so the choice is made on evidence, not on the day's
mood: if more than roughly a quarter of the shared lines need fencing, take the fallback.

### 4.3 Phase 1 — helper scripts become cross-platform Python

`uv` is already a hard requirement, so Python scripts add no new dependency and one implementation
serves both platforms. The five bash scripts are replaced, not shadowed:

- `scripts/install_bepinex.py` — selects the flavour by target platform (Linux Mono BepInEx 5
  5.4.23.5 as today; Windows IL2CPP BepInEx 6 at the build Phase 0 pins), verifies a pinned sha256
  per artifact exactly as the bash version does today, unzips into the game folder, and applies the
  `executable_name` patch to `run_bepinex.sh` on Linux only.
- `scripts/deploy_mod.py` — builds the csproj for the target runtime and copies the DLL, plus
  Newtonsoft.Json for the IL2CPP flavour.
- `scripts/dump_game.py` — replaces `decompile.sh`: `ilspycmd` against `VampireSurvivors.Runtime.dll`
  for Mono, Il2CppInterop assembly generation against `GameAssembly.dll` + `global-metadata.dat` for
  IL2CPP. Output stays in the git-ignored `decompiled/`, which remains poncle's code and must not be
  committed.
- `scripts/game_ctl.py` — launch/stop/status/log/wait-log for three cases: Linux native, Windows
  native, and the Proton-hosted Windows build used for verification.
- `scripts/fake_plugin.py` — already Python; audited for POSIX assumptions.

`.github/workflows/shellcheck.yml` is deleted with the last `.sh` file. Every reference to the old
script names is updated: README, CONTRIBUTING, CLAUDE.md, CHANGELOG, `.github/ISSUE_TEMPLATE/*`,
`.github/PULL_REQUEST_TEMPLATE.md`, `.github/dependabot.yml`, SECURITY.md. The historical documents
under `docs/superpowers/plans/` and `docs/superpowers/ledgers/` are **not** rewritten — `docs/README.md`
already says they are historical records, and editing them would falsify the paper trail.

### 4.4 Phase 2 — the IL2CPP plugin

- `mod/JevSurvivors.Il2Cpp/JevSurvivors.Il2Cpp.csproj`: `net6.0`, BepInEx 6 IL2CPP references,
  generated interop assembly references, Newtonsoft.Json from NuGet, no publicizer.
- Shared compilation: the new csproj links `../JevSurvivors/*.cs` for `Transport.cs`, `Movement.cs`,
  `StateSampler.cs`, `MenuDriver.cs` and `Patches.cs`.
- `Aliases.Mono.cs` and `Aliases.Il2Cpp.cs`, one per project, carrying the `global using` lines that
  map every game type to its per-runtime namespace.
- `Plugin.Mono.cs` / `Plugin.Il2Cpp.cs`: the entry point is the one genuinely divergent file
  (`BaseUnityPlugin` + `Awake` versus `BasePlugin` + `Load`, and `AddUnityComponent<T>()` for the
  injected `MenuDriver`/tick behaviours).
- `#if IL2CPP` is confined to coroutine starts (the `StartCoroutine` extension in BepInEx 6's
  IL2CPP utils namespace, whichever of the two Phase 0 pins) and type injection. Anything needing
  more fencing than that is evidence for the Phase 0 fallback.
- `mod/Directory.Build.props` gains platform-aware `GameDir` defaults, including the Windows Steam
  default `C:\Program Files (x86)\Steam\steamapps\common\Vampire Survivors`.

### 4.5 Phase 3 — brain, CI, documentation

- `__main__.py`: `loop.add_signal_handler` wrapped so `NotImplementedError` falls back to
  `signal.signal`, with a comment saying why (Windows' event loop has no signal handler support).
- CI: `windows-latest` added to the brain job's matrix. The plugin still cannot be built in CI on
  any platform — the game assemblies are not redistributable — and the existing comment in
  `ci.yml` explaining that stays true for both flavours.
- README: Platform support rewritten, the Linux-only badge replaced, a Windows setup path added
  alongside the Linux one, Known limitations updated. CONTRIBUTING gains the Windows build and
  verification steps. CLAUDE.md's Commands and "What can't be verified here" sections updated.
  CHANGELOG gets an entry.

### 4.6 What "verified" is allowed to mean

- The Linux plugin keeps its existing verification: `deploy_mod` plus a human launching the game and
  watching `BepInEx/LogOutput.log`. Part B must not regress it, and a full Linux smoke run is part
  of the definition of done.
- The IL2CPP plugin is verified by a Proton smoke run on this machine: a run that starts from the
  main menu, picks a character and stage, plays, and ends.
- Both smoke runs need a human at a GUI Steam session and cannot be done from a coding session, the
  same constraint CLAUDE.md already records for the Linux plugin. A plan task that ends in "launch
  the game and watch" is a request for the human, and its result is reported, not assumed.
- **Nothing here is verified on real Windows hardware.** Every claim in README, CHANGELOG and commit
  messages says "verified under Proton on Linux" and not "works on Windows", and the issue templates
  invite Windows users to report the difference. This follows the repo's existing rule about not
  quietly upgrading code-reviewed paths to "works".

### 4.7 Risks

- **Steam API init under Proton** may fail outside the Steam client, blocking Phase 0 step 2. Known
  mitigations are adding the Windows copy to Steam as a non-Steam shortcut with a Proton
  compatibility tool, or `umu-launcher`. If none work, the port falls back to "full port,
  unverified" and that change of status is reported, not absorbed.
- **Harmony on IL2CPP** may fail to patch methods that are inlined or stripped. `Patches.cs` is the
  file most exposed; Phase 0 step 5 is the early warning.
- **Two loaders, two BepInEx majors.** A user with both builds could point `GAME_DIR` at the wrong
  one; `install_bepinex.py` and `deploy_mod.py` detect which build a folder holds (ELF versus PE,
  `Managed/` versus `il2cpp_data/`) and refuse to install the wrong flavour.
- **Script rewrite regression.** The bash scripts work today. Each Python replacement is verified by
  running it against the real Linux install before the corresponding `.sh` is deleted.

## 5. Out of scope

- macOS.
- Shipping Proton as a supported way for end users to play.
- Any change to the digest, the questions, the thresholds, or the wire protocol.
- Pinning anything other than character and stage (level-up and arcana picks stay Jev's).
- Rewriting the historical documents in `docs/superpowers/plans/` and `docs/superpowers/ledgers/`.

## 6. Sequencing

Part A first: it is self-contained, fully testable offline, and useful on its own. Then Part B's
Phase 0, whose result decides the shape of Phases 1-3.

The two parts get two implementation plans, not one. They share no code, and Part B's plan cannot be
written past Phase 0 in any detail until the spike reports.

## 7. References

- BepInEx 6 documentation, v6.0.0-pre.1: `BasePlugin`, `MonoBehaviourExtensions.StartCoroutine`,
  `IL2CPPChainloader.AddUnityComponent<T>` — https://docs.bepinex.dev/v6.0.0-pre.1/
- Il2CppInterop — https://github.com/BepInEx/Il2CppInterop
- The original design doc, whose section 2 records the Mono-side member names this port must find
  IL2CPP equivalents for: `docs/superpowers/specs/2026-09-17-jev-vampire-survivors-design.md`
