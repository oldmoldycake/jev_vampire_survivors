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

- [ ] **Download the Windows depot into a fresh directory**

```bash
mkdir -p ~/games/vs-windows
steamcmd +@sSteamCmdForcePlatformType windows \
         +login <your-steam-account> \
         +force_install_dir ~/games/vs-windows \
         +app_update 1794680 validate \
         +quit
```

It will prompt for the password and Steam Guard code. **Before running steamcmd, check the target is not inside a Steam library.** This exact command
with `force_install_dir` pointing into `~/.local/share/Steam/steamapps/common` overwrote the
Linux install on 2026-09-18 and cost a re-download:

```bash
T=~/games/vs-windows
case "$(readlink -m "$T")" in
  *"/Steam/steamapps/"*|*"/steamapps/common/"*)
    echo "REFUSING: $T is inside a Steam library" >&2 ;;
  *) echo "target ok: $(readlink -m "$T")" ;;
esac
file ~/.local/share/Steam/steamapps/common/"Vampire Survivors"/VampireSurvivors.exe   # ELF, before
```

If the files land in steamcmd's own `steamapps/` rather than the target, re-run with
`+force_install_dir` before `+login` — **after** re-checking the target with the case statement
above. Then confirm the Steam install is still an ELF with the same `file` command.

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

```markdown
# Windows Phase 0 spike: findings (YYYY-MM-DD)

| Criterion | Result | Evidence |
| --- | --- | --- |
| 1. Separate Windows copy exists | pass / fail | `file` output, path, size |
| 2. Boots under Proton to main menu | pass / fail | which Proton, what was seen |
| 3. BepInEx 6 IL2CPP loads | pass / fail | build string pinned, log excerpt, interop listing |
| 4. Hello-world BasePlugin loads | pass / fail | log line |
| 5. Members survive interop | see table | per-member table above |

**Namespace pin:** BepInEx.IL2CPP | BepInEx.Unity.IL2CPP (from the build in criterion 3)

**Structure decision:** shared source + aliases | two sibling projects
**Because:** <fraction of shared lines needing #if IL2CPP, from the criterion 5 table>

**Stopped at:** <criterion, if any> — <what happened, verbatim>
```

Phases 1-3 get their plan only once this report exists. Spec §6: "Part B's plan cannot be written
past Phase 0 in any detail until the spike reports."
