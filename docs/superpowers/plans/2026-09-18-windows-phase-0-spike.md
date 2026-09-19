# Windows support, Phase 0: spike plan

> **For agentic workers:** This is a throwaway spike, not a feature. Its deliverable is the
> findings report in §6 — evidence, not code. Nothing built here is kept. Steps use checkbox
> (`- [ ]`) syntax for tracking.

**Goal:** Answer whether an IL2CPP port of the plugin is *verifiable on this machine* before any
of it is written, and gather the evidence that decides its structure.

**Architecture:** Five exit criteria in order (spec §4.2). Each one that fails stops the phase and
gets reported rather than worked around. Two of them can only be done by a human at a GUI Steam
session; the rest are agent work that cannot start until those report.

**Tech Stack:** steamcmd, Proton (Experimental / 9.0 / 10.0 / 11.0 installed), BepInEx 6 IL2CPP,
Il2CppInterop + Cpp2IL, .NET 6 SDK.

**Spec:** `docs/superpowers/specs/2026-09-18-windows-support-and-pinned-picks-design.md` §4.2,
with the risk register in §4.7 and the verification rules in §4.6.

## Global Constraints

- **Never point any of this at the existing Linux install.** `~/.local/share/Steam/steamapps/
  common/Vampire Survivors` is the verified, working one. The Windows depot goes in a separate
  directory and the Linux install is never switched to it (spec §4.2 step 1).
- **Nothing generated here is committed.** Interop assemblies, Cpp2IL output and decompiled code
  are poncle's code; they live in the git-ignored `decompiled/` or outside the repo entirely.
- **A step ending in "launch the game and watch" is a request for the human.** Its result is
  reported, not assumed (CLAUDE.md; spec §4.6).
- **Phases 1-3 do not start here.** Not a script rewrite, not a csproj, not an alias file. The
  only artefact this phase produces is §6's report.
- **Nothing learned here upgrades a README claim to "works on Windows".** Everything verified in
  this phase is "verified under Proton on Linux" at most (spec §4.6).

## The decision this spike exists to make

Spec §4.2's decision point: **shared source + per-project `global using` alias files + a few
`#if IL2CPP` blocks**, or the fallback of **two independent sibling projects with deliberate
duplication**.

The criterion, recorded in advance so the choice is made on evidence: *if more than roughly a
quarter of the shared lines need fencing, take the fallback.* Exit criterion 5 is what feeds it.

---

## What the current docs say (retrieved 2026-09-18 via Context7)

Three things worth having straight before the spike runs, two of which correct or sharpen the
spec:

1. **`BepInEx.IL2CPP` is the right namespace for v6.0.0-pre.1** — `BasePlugin` + `override void
   Load()`, with `Log.LogInfo(...)` rather than `Logger.LogInfo(...)`. The spec's open question
   about `BepInEx.IL2CPP` vs `BepInEx.Unity.IL2CPP` resolves to the former *for pre.1
   specifically*; a later bleeding-edge build is the other. Criterion 3 pins which build we are
   actually on, so this stays a Phase 0 output, not an assumption.
2. **`BasePlugin.AddComponent<T>()` exists** alongside `IL2CPPChainloader.AddUnityComponent<T>()`,
   and is the simpler of the two for the plugin's injected behaviours. Worth noting for Phase 2;
   the spec only mentions the chainloader form.
3. **Interop generation is two steps, not one, and needs Unity base libraries.** The spec (§4.3)
   describes "Il2CppInterop assembly generation against `GameAssembly.dll` +
   `global-metadata.dat`". The documented pipeline is:

   ```bash
   Cpp2IL --game-path <game dir> --exe-name <exe> --skip-analysis --skip-metadata-txts --disable-registration-prompts
   il2cppinterop generate --input <cpp2il_out> --output <dir> --unity <unity base libs> --game-assembly <GameAssembly.dll>
   ```

   The `--unity` argument is managed Unity core libraries (`UnityEngine.dll` and friends) matching
   the game's Unity version. That is a real prerequisite the spec's one-liner hides, and it is
   what `scripts/dump_game.py` would have to arrange in Phase 1.

**Not doc-verified:** steamcmd's flag ordering. Context7 carries no steamcmd documentation, so the
command in H1 comes from Valve's published flags and common usage, with a fallback noted. Treat a
wrong install location as an ordering problem, not a failure.

---

## Step H1 (human): download a separate Windows copy

**Exit criterion 1.** Needs an interactive Steam login, so an agent cannot do it.

- [ ] **Install steamcmd if it isn't there**

`steamcmd` is **not in the Arch/CachyOS repos** — it is AUR-only, so `pacman -S steamcmd` fails
with "target not found". Use an AUR helper (this machine has both `paru` and `yay`):

```bash
command -v steamcmd || paru -S steamcmd
```

It is a wrapper around Valve's own bootstrap: the first `steamcmd` run downloads the real client
into `~/.steam/steamcmd/` before doing anything else, so expect a self-update pass.

- [ ] **Check the target is not inside a Steam library — before anything downloads**

A `force_install_dir` pointing into `~/.local/share/Steam/steamapps/common` would overwrite the
verified Linux install with the Windows depot. That hazard is real but is *not* what happened on
2026-09-18 — see the box below. Run the check anyway; it costs nothing and the failure mode is a
re-download:

```bash
T=~/games/vs-windows
case "$(readlink -m "$T")" in
  *"/Steam/steamapps/"*|*"/steamapps/common/"*)
    echo "REFUSING: $T is inside a Steam library" >&2 ;;
  *) echo "target ok: $(readlink -m "$T")" ;;
esac
file ~/.local/share/Steam/steamapps/common/"Vampire Survivors"/VampireSurvivors.exe   # ELF, before
```

Expected: `target ok: /home/<you>/games/vs-windows`, and the Steam install reporting `ELF 64-bit`.
A `REFUSING:` line means stop and choose a different target.

If that `file` command reports `PE32+` instead of `ELF 64-bit`, the Linux install is currently
overwritten — restore it before running anything below, per
`docs/superpowers/plans/2026-09-18-linux-install-recovery.md`.

- [ ] **Download the Windows depot into that directory**

Run this in the same shell as the preflight above, so `$T` is still set.

```bash
mkdir -p "$T"
steamcmd +@sSteamCmdForcePlatformType windows \
         +login <your-steam-account> \
         +force_install_dir "$T" \
         +app_update 1794680 validate \
         +quit
```

It will prompt for the password and Steam Guard code. If the files land in steamcmd's own
`steamapps/` rather than the target, re-run with `+force_install_dir` before `+login` — after
re-running the preflight above. Then confirm the Steam install is still an ELF with the same `file`
command.

- [ ] **Check what arrived and report it**

```bash
file ~/games/vs-windows/VampireSurvivors.exe
ls ~/games/vs-windows/GameAssembly.dll ~/games/vs-windows/UnityPlayer.dll
ls ~/games/vs-windows/VampireSurvivors_Data/il2cpp_data/Metadata/global-metadata.dat
ls -d ~/games/vs-windows/VampireSurvivors_Data/Managed 2>/dev/null && echo "UNEXPECTED: Mono build"
du -sh ~/games/vs-windows
```

**Pass:** `VampireSurvivors.exe` is `PE32+ executable (GUI) ... for MS Windows`, the two DLLs and
`global-metadata.dat` exist, and there is **no** `VampireSurvivors_Data/Managed/`.

**Fail → stop and report.** A Mono `Managed/` directory here means the platform override did not
take and the whole port's premise needs re-checking.

## Step H2 (human): boot it under Proton

**Exit criterion 2.** Needs a GUI Steam session.

> **Never force a Steam Play compatibility tool on Vampire Survivors itself (app `1794680`).**
> This is what actually destroyed the Linux install on 2026-09-18: forcing a compatibility tool
> makes Steam install that app's *Windows* depot into the same directory, replacing the Linux
> payload in place — the ELF becomes a PE32+ and `Managed/` and `MonoBleedingEdge/` are pruned,
> which leaves the plugin unbuildable. Recovery is to untick the compatibility tool and let Steam
> re-download the Linux depot.
>
> The Windows copy is run as a **separate non-Steam shortcut** pointing at
> `~/games/vs-windows/VampireSurvivors.exe`, exactly as below. That is safe: the shortcut has its
> own app id and its own compatibility setting, and touches nothing in the Steam library entry.

- [ ] **Make sure the app id file is there** (helps Steam API init outside the client)

```bash
grep -r . ~/games/vs-windows/steam_appid.txt || echo 1794680 > ~/games/vs-windows/steam_appid.txt
```

- [ ] **Add it to Steam and run it under Proton**

In Steam: *Games → Add a Non-Steam Game → Browse →* `~/games/vs-windows/VampireSurvivors.exe`.
Then right-click it → *Properties → Compatibility → Force the use of a specific Steam Play
compatibility tool →* **Proton Experimental**. Launch it.

- [ ] **Report what happened**

One of: reaches the main menu / window opens then closes / never opens / Steam API error. If it
fails, the console output helps:

```bash
~/.local/share/Steam/steamapps/common/'Proton Experimental'/proton run ~/games/vs-windows/VampireSurvivors.exe
```

**Pass:** the main menu is on screen.

**Fail → stop and report.** Spec §4.7 names the mitigations to try in order: the non-Steam
shortcut above, then `umu-launcher`. If neither works, the port's status becomes "full port,
unverified" and that is reported as a change of status, not absorbed silently.

---

## Steps A1-A4 (agent): only after H1 and H2 report

Each of these is written out so it can be executed without re-deriving it, but **none of them
starts before the human steps report an actual result.**

- [ ] **A1 — install BepInEx 6 IL2CPP (exit criterion 3, part 1)**

Download the x64 IL2CPP build for Windows, verify its sha256 against the checksum published on the
release page, unzip into `~/games/vs-windows/`. Record the exact build string — that is the pin
the whole port depends on, and it decides the `BepInEx.IL2CPP` vs `BepInEx.Unity.IL2CPP` question
above. Never unzip an unverified archive into a game folder; `scripts/install_bepinex.sh` already
sets this precedent.

- [ ] **A2 — first run generates interop assemblies (exit criterion 3, part 2)**

Relaunch (human, GUI) with `WINEDLLOVERRIDES="winhttp=n,b"` set for the process. Then check:

```bash
ls ~/games/vs-windows/BepInEx/LogOutput.log
ls ~/games/vs-windows/BepInEx/interop/ | head -30
```

**Pass:** `LogOutput.log` exists and `BepInEx/interop/` holds generated assemblies (expect
`Assembly-CSharp.dll`, `UnityEngine.*.dll`, and `VampireSurvivors.Runtime.dll` or its IL2CPP
equivalent).

- [ ] **A3 — hello-world plugin loads (exit criterion 4)**

A single `net6.0` class library, `BasePlugin` + `Load()`, one `Log.LogInfo` line, built against
the A1 build's references and dropped in `BepInEx/plugins/`. Relaunch (human, GUI) and grep the
log for the line. Nothing else goes in it — this is not the port.

- [ ] **A4 — survey the members the plugin needs (exit criterion 5)**

Against `BepInEx/interop/`, confirm each of these is present, renamed, or gone:

| Member | Used by | Present? | Notes |
| --- | --- | --- | --- |
| `CharacterSelectionPage._characterItemUIs` | MenuDriver | | |
| `StageSelectPage._spawned` | MenuDriver | | |
| `LevelUpPage._spawnedItems` | MenuDriver | | |
| `CharacterController._currentDirectionRaw` | Movement | | |
| `Stage.GetAllEnemiesInScreenBounds` | StateSampler | | |

Also record, for each: the declaring namespace, whether the member is a field or property after
interop generation, and whether its type differs from the Mono side. Those three facts are what
the alias-vs-duplication decision turns on — a namespace difference an alias absorbs, a shape
difference it does not.

**This step can start before H1.** Per spec §2, `GameAssembly.dll` and `global-metadata.dat` for
the Windows build are *already on this machine* inside the Linux install, so the interop
assemblies can be generated with the Cpp2IL → il2cppinterop pipeline above without any depot
download. That would answer criterion 5 — the one that decides the port's structure — while H1
and H2 are still pending. It needs a `--unity` directory of Unity base libraries matching the
game's Unity version, and the output goes somewhere git-ignored. **Ask before running it:** it is
agent work that the "write the plan and stop" instruction covers.

---

## §6 Findings report (the deliverable)

**Run 2026-09-18, 23:20-23:30. All five criteria answered. No criterion failed.**

| Criterion | Result | Evidence |
| --- | --- | --- |
| 1. Separate Windows copy exists | **pass** | `~/games/vs-windows/VampireSurvivors.exe` is `PE32+ executable (GUI), x86-64`; `GameAssembly.dll` 182M, `global-metadata.dat` 51M, no `VampireSurvivors_Data/Managed/`; 1.2G, outside every Steam library |
| 2. Boots under Proton | **pass** | ran as a non-Steam shortcut under Proton Experimental; human-confirmed |
| 3. BepInEx 6 IL2CPP loads | **pass, but only on a bleeding-edge build** | `BepInEx 6.0.0-be.788`, `System platform: Windows 10 (Wine 11.0) 64-bit`, `Runtime version: 6.0.7`, 202 interop assemblies generated into `BepInEx/interop/` |
| 4. Hello-world `BasePlugin` loads | **pass** | `Loading [JevHello 0.1.0]` -> `JEVHELLO: BasePlugin.Load reached`, `runtime=6.0.7, os=Microsoft Windows NT 10.0.19045.0`, `Chainloader startup complete`, zero errors |
| 5. Hooked members survive interop | **pass, all five** | see the table below |

### Criterion 3's real finding: a tagged release cannot work

The game is **Unity 6000.0.62f1**, whose IL2CPP metadata is **version 31**. BepInEx's current tagged
release (`v6.0.0-pre.2`, which reports internally as `be.697`) bundles a Cpp2IL supporting metadata
**23-29** and fails outright:

```
Failed to generate Il2Cpp interop assemblies: LibCpp2ILInitializationException
System.FormatException: Unsupported metadata version found! We support 23-29, got 31
```

`BepInEx 6.0.0-be.788` from builds.bepinex.dev bundles a Cpp2IL supporting **23-106** and generates
all 202 interop assemblies. The same failure would hit any Windows user following a README that
said "install BepInEx 6", so the build must be pinned to a bleeding-edge artifact and said plainly.

- Pinned artifact: `BepInEx-Unity.IL2CPP-win-x64-6.0.0-be.788+5b766a3.zip`
- sha256 `f4cc496bd098a0df4164b81e3737297707f13a47c2478dba2f60eefab784817a`
- Launch option that makes the doorstop load under Proton: `WINEDLLOVERRIDES="winhttp=n,b" %command%`

**Namespace pin:** `BepInEx.Unity.IL2CPP` (not pre.1's `BepInEx.IL2CPP`). Confirmed from the shipped
`BepInEx.Unity.IL2CPP.xml`: `M:BepInEx.Unity.IL2CPP.BasePlugin.AddComponent``1` and
`M:BepInEx.Unity.IL2CPP.IL2CPPChainloader.AddUnityComponent``1`. The bundled runtime is .NET
**6.0.7**, so `net6.0` is the right `TargetFramework`, as spec §4.4 assumed.

### Criterion 5: the member survey

| Member | Present | Shape under interop |
| --- | --- | --- |
| `CharacterSelectionPage._characterItemUIs` | yes | property `_characterItemUIs` (`get__`/`set__` accessors + `NativeFieldInfoPtr__`) |
| `StageSelectPage._spawned` | yes | same shape |
| `LevelUpPage._spawnedItems` | yes | same shape |
| `CharacterController._currentDirectionRaw` | yes | same shape |
| `Stage.GetAllEnemiesInScreenBounds` | yes | method, name unchanged |

All five live in `VampireSurvivors.Runtime.dll` — the same assembly name as the Mono build. Il2CppInterop
turns each private field into a **property of the same name**, so `page._characterItemUIs` is valid C#
against both runtimes: a publicized field on Mono, a property on IL2CPP. The five hooks need no alias
and no `#if` at all.

Namespaces are identical between the two builds (`VampireSurvivors.*`, unprefixed in both), and the
`UnityEngine.*Module.dll` assemblies keep their names. The only assembly that is renamed is
`mscorlib.dll` -> `Il2Cppmscorlib.dll`.

### Structure decision: shared source + aliases (spec §4.2's primary option)

**Not** the two-sibling-projects fallback. The criterion recorded in advance was "if more than roughly a
quarter of the shared lines need fencing, take the fallback". Measured divergence is far below that:

1. the entry point (`BaseUnityPlugin`+`Awake` vs `BasePlugin`+`Load`) — one file per project, already
   planned as such in spec §4.4;
2. BCL types in game signatures coming from `Il2Cppmscorlib` (`Il2CppSystem.*`) — what the
   `global using` alias files exist to absorb;
3. coroutine starts and type injection — the `#if IL2CPP` blocks spec §4.4 already budgets for;
4. `Newtonsoft.Json` from NuGet instead of the game's copy, as spec §2 predicted.

`Patches.cs` was flagged in spec §4.7 as the file most exposed to Harmony-on-IL2CPP problems. Criterion 5
gives it no early warning: every member it needs survived, and `Il2CppInterop.HarmonySupport.dll` ships in
the pinned build. That risk stays open until Phase 2 actually patches something.

### What this does NOT establish

- Nothing was verified on real Windows hardware. Everything above is "verified under Proton on Linux",
  per spec §4.6, and README must say exactly that.
- The game was launched to the point where BepInEx loaded and a plugin ran. A full run under the real
  plugin — menus driven, a stage played, game over — has not happened on the IL2CPP side.
- Harmony patching of game methods under IL2CPP is untested.

