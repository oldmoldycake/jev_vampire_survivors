# Linux install recovery: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get the Steam install back to the Linux Mono build so the plugin can be built, deployed
and smoke-run again, and make the mistake that broke it loud instead of silent next time.

**Architecture:** One human step restores the depot; everything after it is verification against
the exact files the build needs. The repo change is a single guard in the two scripts that touch
the game folder, tested against both real builds now present on this machine — the restored Mono
install as the positive fixture, `~/games/vs-windows` as the negative one.

**Tech Stack:** Steam client, bash, .NET 8 SDK (`~/.dotnet/dotnet`, 8.0.425), BepInEx 5.4.23.5.

**Spec:** `docs/superpowers/specs/2026-09-18-windows-support-and-pinned-picks-design.md` — §2
(the verified-facts section this breakage falsified), §4.2 step 1 (the constraint that was
violated), §4.6 (why a working Linux install is part of Part B's definition of done), §4.7 (the
wrong-flavour guard, planned there for Phase 1).

## The errors this plan fixes

| # | Error | Evidence |
| --- | --- | --- |
| E1 | The Steam install holds the **Windows IL2CPP build**, not the Linux Mono build | `VampireSurvivors.exe` is `PE32+ ... MS Windows`, mtime 2026-09-18 21:03; `VampireSurvivors_Data/Managed/` and `MonoBleedingEdge/` are gone; `GameAssembly.dll` untouched since Sept 11 |
| E2 | The plugin cannot be built or deployed | `mod/Directory.Build.props` sets `ManagedDir = $(GameDir)/VampireSurvivors_Data/Managed`; `JevSurvivors.csproj:23-32` references 10 assemblies from it, all missing |
| E3 | Spec §2's first bullet is false for this machine | It records the folder as holding both builds, ELF exe included |
| E4 | The Phase 0 H1 instruction is what caused E1 and is still dangerous as written | `docs/superpowers/plans/2026-09-18-windows-phase-0-spike.md` H1 tells the reader to retry with `+force_install_dir` moved, with no check that the target is outside the Steam library |
| E5 | Nothing in the repo notices a wrong-flavour game folder | `deploy_mod.sh:14` checks only for `BepInEx/core/BepInEx.dll`, so E1 surfaces as an unresolvable MSBuild reference |

**Not an error, ruled out while investigating:** dotnet. `deploy_mod.sh:5` already does
`export PATH="$HOME/.dotnet:$PATH"` and the SDK is installed there (8.0.425). Only a bare
`dotnet` in a non-fish interactive shell needs the path; no change required.

## Global Constraints

- **The Steam install is the only verified Linux game folder.** Nothing in this plan points
  steamcmd, an installer or a build at it except through the Steam client itself.
- **Never run steamcmd with `+@sSteamCmdForcePlatformType` against a directory inside a Steam
  library.** That is what produced E1.
- **`~/games/vs-windows` stays as it is.** It passed Phase 0 criterion 1 and is the negative
  fixture in Task 3; re-downloading it wastes 1.2G.
- **A plugin change is "reviewed, not verified" until a human launches the game and watches
  `<game>/BepInEx/LogOutput.log`** (CLAUDE.md). Task 2's smoke run is a request for the human.
- **Commits:** Conventional Commits, lowercase imperative subject, no trailing period, scope
  `mod` for plugin code and `scripts`/none for the rest. Attribution trailers as in the commit
  steps below.
- **Do not edit anything under `docs/superpowers/ledgers/`,** or the two historical plans
  (`2026-09-17-jev-vs-brain.md`, `2026-09-17-jev-vs-plugin.md`).

---

## File Structure

| File | Responsibility |
| --- | --- |
| `scripts/deploy_mod.sh` | Gains a build-flavour guard before `dotnet build`: refuses a folder with no `VampireSurvivors_Data/Managed/VampireSurvivors.Runtime.dll` and says what to do about it. |
| `scripts/install_bepinex.sh` | Same guard, same wording: BepInEx 5 Linux must not be unpacked into an IL2CPP folder. |
| `docs/superpowers/specs/2026-09-18-windows-support-and-pinned-picks-design.md` | §2 gains a dated correction recording that the folder was overwritten and what it holds now. |
| `docs/superpowers/plans/2026-09-18-windows-phase-0-spike.md` | H1 gains a preflight that refuses a `force_install_dir` target inside a Steam library, plus a before/after fingerprint of the Steam install. |
| `CHANGELOG.md` | One `Fixed` line for the guard, under `[Unreleased]`. |

No Python changes: the brain never touches the game folder, and Part A is unaffected by all of
this.

---

## Task 0: Branch

The Part A branch (`feat/pinned-character-and-stage`) is finished but still unmerged, and this
work is unrelated to it. Branch from `main` so the two can land independently.

- [ ] **Step 1: Branch off main**

```bash
cd /home/oldmoldycake/Projects/jev_vampire_survivors
git switch main
git switch -c fix/linux-install-recovery
git branch --show-current
```

Expected: `fix/linux-install-recovery`. The Part A branch is untouched and still has its six
commits.

---

## Task 1: Restore the Linux Mono build

Fixes E1 and E2. **Step 1 is the human's; nothing else in this plan works until it reports.**

**Files:** none in the repo. This task changes the game folder only.

**Interfaces:**
- Consumes: nothing.
- Produces: a Steam install holding the Mono build — the positive fixture Tasks 2 and 3 need.

- [ ] **Step 1 (human): remove the Steam Play compatibility tool — DONE 2026-09-18 22:45**

**This step originally said to verify integrity of game files. That was the wrong remedy**, aimed
at a cause that turned out to be wrong. A verify would have re-checked the folder against whatever
platform Steam thought the app was on, and Steam thought it was on Windows.

The actual cause: Vampire Survivors was mapped to `GE-Proton11-1` in Steam's `CompatToolMapping`
(`~/.local/share/Steam/config/config.vdf`). Forcing a compatibility tool makes Steam install the
app's *Windows* depot into the same directory, which is what replaced the Linux payload in place.

The remedy, which is what was actually done: **Library → Vampire Survivors → right-click →
Properties → Compatibility → untick "Force the use of a specific Steam Play compatibility tool".**
Steam then re-downloads the Linux depot on its own.

Verified after the fact: `1794680` is gone from `CompatToolMapping`, and the appmanifest reports
`StateFlags 4` with `BytesDownloaded == BytesToDownload`.

Files BepInEx added (`BepInEx/`, `run_bepinex.sh`, `libdoorstop.so`) are not in Steam's manifest
and are left alone by a verify — the plugin at `BepInEx/plugins/JevSurvivors/JevSurvivors.dll`
and the config in `BepInEx/config/` survive.

Report: whether the verify found files to replace, and whether it completed.

**If the verify reports everything as already valid** and the checks in Step 2 still fail, the
fallback is to uninstall and reinstall the game from Steam — a full 1.2G, and the BepInEx files
would need reinstalling afterwards with `scripts/install_bepinex.sh`. Don't reach for it first.

- [ ] **Step 2: Verify the restore against what the build actually needs**

```bash
L=~/.local/share/Steam/steamapps/common/"Vampire Survivors"
file "$L/VampireSurvivors.exe"
ls -d "$L/MonoBleedingEdge" "$L/VampireSurvivors_Data/Managed"
for a in VampireSurvivors.Runtime PauseSystem PhaserPort Zenject UnityEngine \
         UnityEngine.CoreModule UnityEngine.InputLegacyModule UnityEngine.UI \
         Unity.TextMeshPro Newtonsoft.Json; do
  [ -f "$L/VampireSurvivors_Data/Managed/$a.dll" ] && echo "  ok  $a.dll" || echo "  MISSING  $a.dll"
done
```

Expected: `VampireSurvivors.exe` is `ELF 64-bit LSB ... x86-64`, both directories exist, and all
ten assemblies print `ok`. Those ten are exactly the `<Reference>` hint paths in
`mod/JevSurvivors/JevSurvivors.csproj:23-32`; a missing one breaks the build.

- [ ] **Step 3: Confirm BepInEx survived the verify**

```bash
L=~/.local/share/Steam/steamapps/common/"Vampire Survivors"
ls "$L/BepInEx/core/BepInEx.dll" "$L/BepInEx/plugins/JevSurvivors/JevSurvivors.dll"
ls "$L/BepInEx/config/dev.oldmoldycake.jevsurvivors.cfg"
grep -n '^executable_name=' "$L/run_bepinex.sh"
```

Expected: all present, and `executable_name="VampireSurvivors.exe"` on line 13 — the patch
`install_bepinex.sh` applies. If `run_bepinex.sh` or `libdoorstop.so` is gone, re-run
`scripts/install_bepinex.sh`; it is safe to re-run.

No commit: nothing in the repo changed.

---

## Task 2: Prove the toolchain works end to end

Confirms E2 is closed. Build and deploy are agent work; the run is the human's.

**Files:** none in the repo.

**Interfaces:**
- Consumes: the restored install from Task 1.
- Produces: a freshly built `JevSurvivors.dll` in the game's plugins folder, and a human-observed
  log line proving it loads.

- [ ] **Step 1: Build and deploy**

```bash
cd /home/oldmoldycake/Projects/jev_vampire_survivors
scripts/deploy_mod.sh
```

Expected: `Build succeeded`, then `deployed <game>/BepInEx/plugins/JevSurvivors/JevSurvivors.dll`.
The script puts `~/.dotnet` on PATH itself, so no shell setup is needed.

**If the build fails on an unresolvable reference,** Task 1 did not fully restore — go back to
Task 1 Step 2 and find which of the ten assemblies is missing rather than editing the csproj.

- [ ] **Step 2: Note the deployed timestamp, so the smoke run is provably the new build**

```bash
ls -la --time-style=long-iso ~/.local/share/Steam/steamapps/common/"Vampire Survivors"/BepInEx/plugins/JevSurvivors/JevSurvivors.dll
```

Expected: today's date and the current time, not `2026-09-18 15:03` (the build that predates the
breakage).

- [ ] **Step 3 (human): smoke run**

Start the brain, then launch the game from Steam and watch the log:

```bash
# terminal 1
cd /home/oldmoldycake/Projects/jev_vampire_survivors/brain && uv run --env-file ../.env jev-vs
# terminal 2
tail -f ~/.local/share/Steam/steamapps/common/"Vampire Survivors"/BepInEx/LogOutput.log
```

Expected in the log: the plugin's load line, then `page shown: ...` entries, then a run starting —
the shape the pre-breakage log already shows (`run started: PORTA on MOLISE` at 18:15 today).

Report what the log said. Per CLAUDE.md this is the only thing that makes a plugin change
verified rather than reviewed; an agent cannot do it.

No commit: nothing in the repo changed.

---

## Task 3: Make a wrong-flavour game folder a clear error

Fixes E5. Spec §4.7 plans this for Phase 1's Python rewrite; this is the minimal bash version,
landing now because the failure it describes just happened for real. The Phase 1 rewrite carries
the same logic over rather than inventing it.

**Files:**
- Modify: `scripts/deploy_mod.sh:13-14` (between the dotnet check and the BepInEx check)
- Modify: `scripts/install_bepinex.sh` (after `GAME_DIR` is resolved)
- Modify: `CHANGELOG.md` (`[Unreleased]` → `Fixed`)

**Interfaces:**
- Consumes: `~/games/vs-windows` as the IL2CPP fixture, the restored Steam install as the Mono
  fixture.
- Produces: both scripts exit 1 with a named cause when `GAME_DIR` holds an IL2CPP build.

- [ ] **Step 1: Write the guard in `scripts/deploy_mod.sh`**

Insert **before** the existing BepInEx check on line 14, after the dotnet check closes. Order
matters: pointed at the IL2CPP copy, "this is the wrong build" is the true cause, while "BepInEx
not installed" is a true statement that sends the reader down the wrong path.

```bash
# Both builds ship under the same folder name and steamcmd with a platform override will swap one
# for the other in place. Absence of Managed/ is the reliable test: the Mono install also carries
# the Windows IL2CPP payload (GameAssembly.dll, il2cpp_data), so those prove nothing on their own.
if [ ! -f "$GAME_DIR/VampireSurvivors_Data/Managed/VampireSurvivors.Runtime.dll" ]; then
  echo "$GAME_DIR does not hold the Linux Mono build." >&2
  echo "VampireSurvivors_Data/Managed/VampireSurvivors.Runtime.dll is missing, and this plugin is built against it." >&2
  if [ -d "$GAME_DIR/VampireSurvivors_Data/il2cpp_data" ] && [ ! -d "$GAME_DIR/VampireSurvivors_Data/Managed" ]; then
    echo "This looks like the Windows IL2CPP build. Restore the Linux one:" >&2
    echo "  Steam -> Vampire Survivors -> Properties -> Installed Files -> Verify integrity of game files" >&2
  fi
  exit 1
fi
```

- [ ] **Step 2: Run it against the IL2CPP folder and watch it refuse**

```bash
cd /home/oldmoldycake/Projects/jev_vampire_survivors
GAME_DIR="$HOME/games/vs-windows" scripts/deploy_mod.sh; echo "exit=$?"
```

Expected: `exit=1`, the message names `VampireSurvivors.Runtime.dll`, and the "looks like the
Windows IL2CPP build" hint with the Steam verify instruction appears. No `dotnet build` runs, and
the BepInEx message does **not** appear — the flavour guard fires first, which is the point of
placing it above that check.

- [ ] **Step 3: Run it against the restored install and watch it build**

```bash
cd /home/oldmoldycake/Projects/jev_vampire_survivors
scripts/deploy_mod.sh; echo "exit=$?"
```

Expected: `exit=0` and a deploy line. The guard must be invisible on the happy path.

- [ ] **Step 4: Write the same guard in `scripts/install_bepinex.sh`**

Insert directly after the `GAME_DIR="${GAME_DIR:-...}"` line:

```bash
# This installs the Linux Mono flavour of BepInEx 5. Unpacking it into the Windows IL2CPP build
# produces a game that loads nothing and a folder that is hard to untangle afterwards. The question
# is "is a game here, and is it the wrong flavour", so VampireSurvivors_Data gates the check and
# Managed/ answers it; il2cpp_data only sharpens the message, as in deploy_mod.sh. Testing the
# directory rather than a specific assembly is deliberate: only the build's flavour matters here,
# while deploy_mod.sh must confirm the exact file it compiles against.
if [ -d "$GAME_DIR/VampireSurvivors_Data" ] && [ ! -d "$GAME_DIR/VampireSurvivors_Data/Managed" ]; then
  echo "$GAME_DIR holds a game, but not the Linux Mono build: VampireSurvivors_Data/Managed is missing." >&2
  if [ -d "$GAME_DIR/VampireSurvivors_Data/il2cpp_data" ]; then
    echo "This looks like the Windows IL2CPP build. BepInEx 5 Linux cannot load it." >&2
  fi
  echo "Restore the Linux build first:" >&2
  echo "  Steam -> Vampire Survivors -> Properties -> Installed Files -> Verify integrity of game files" >&2
  exit 1
fi
```

Gating on `VampireSurvivors_Data` keeps a first-time install working whether the target directory
is missing or merely empty — neither is a wrong-flavour folder — while still refusing any folder
that holds a game of the wrong flavour. An earlier draft made `il2cpp_data` part of the firing
condition; that let a game folder with neither directory through, which review caught.

- [ ] **Step 5: Verify both paths of the installer guard**

```bash
cd /home/oldmoldycake/Projects/jev_vampire_survivors
GAME_DIR="$HOME/games/vs-windows" scripts/install_bepinex.sh; echo "exit=$?"
```

Expected: `exit=1` with the IL2CPP message, and **nothing downloaded or unpacked** — confirm
`~/games/vs-windows/BepInEx` still does not exist:

```bash
ls -d ~/games/vs-windows/BepInEx 2>&1
```

Expected: `No such file or directory`.

Then confirm the guard stays out of the way for a first-time install into a directory that does
not exist yet. Test the condition in isolation rather than running the installer, which would
download and unpack BepInEx as a side effect:

```bash
mkdir -p /tmp/empty-target
for d in /tmp/does-not-exist-yet /tmp/empty-target; do
  GAME_DIR="$d" bash -c '
  if [ -d "$GAME_DIR/VampireSurvivors_Data" ] && [ ! -d "$GAME_DIR/VampireSurvivors_Data/Managed" ]; then
    echo "$GAME_DIR: REFUSED (wrong: a fresh install must be allowed)"
  else
    echo "$GAME_DIR: guard inactive, as it should be"
  fi'
done
rmdir /tmp/empty-target
```

Expected: both print `guard inactive, as it should be` — a target directory that does not exist and
one that exists but holds no game are both legitimate first-time installs. Keep this condition
character for character identical to the one in the script — if they drift, this proves nothing.

- [ ] **Step 6: Lint both scripts**

`shellcheck` is not installed on this machine — CI runs it (`.github/workflows/shellcheck.yml`).
Check syntax locally instead:

```bash
bash -n scripts/deploy_mod.sh && bash -n scripts/install_bepinex.sh && echo "syntax ok"
```

Expected: `syntax ok`. CI runs the real shellcheck on push.

- [ ] **Step 7: Changelog**

Under `## [Unreleased]` → `### Fixed`, alongside the entry Part A added (or as a new `### Fixed`
block if this lands first):

```markdown
- `scripts/deploy_mod.sh` and `scripts/install_bepinex.sh` now refuse a game folder holding the
  Windows IL2CPP build instead of failing later with an unresolvable reference or unpacking a
  Mono loader into it, and say how to restore the Linux build.
```

- [ ] **Step 8: Commit**

```bash
cd /home/oldmoldycake/Projects/jev_vampire_survivors
git add scripts/deploy_mod.sh scripts/install_bepinex.sh CHANGELOG.md
git commit -m "fix(scripts): refuse a game folder holding the Windows IL2CPP build

Both builds ship under the same folder name, and steamcmd with a platform
override swaps one for the other in place. Absence of Managed/ is the test:
the Mono install also carries the IL2CPP payload, so that proves nothing.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019VzgtSAh31zbf8s8GCuyaE"
```

---

## Task 4: Correct the record

Fixes E3 and E4. Documentation only — but the spec's §2 is the section a future reader trusts
about this machine, and the Phase 0 plan is the document that caused the damage.

**Files:**
- Modify: `docs/superpowers/specs/2026-09-18-windows-support-and-pinned-picks-design.md` §2,
  first bullet
- Modify: `docs/superpowers/plans/2026-09-18-windows-phase-0-spike.md`, step H1

**Interfaces:**
- Consumes: the Task 1 outcome (what the folder holds after the restore).
- Produces: no code.

- [ ] **Step 1: Record the correction in the spec**

Append to the first bullet of §2's "The game install is two builds in one folder":

```markdown
- **Correction, 2026-09-18 22:00:** this stopped being true during Phase 0 preparation.
  **Observed:** `VampireSurvivors.exe` in this folder is now a PE32+ Windows binary with mtime
  2026-09-18 21:03; `VampireSurvivors_Data/Managed/` and `MonoBleedingEdge/` are gone;
  `GameAssembly.dll` is unchanged since 2026-09-11; and `appmanifest_1794680.acf` carries no
  `platform_override` keys with `LastUpdated` 2026-09-11, so the Steam client did not do it.
  **Most likely cause, not observed:** a steamcmd run with `+@sSteamCmdForcePlatformType windows`
  whose `force_install_dir` still pointed at the Steam library, which would rewrite only the
  differing files (the 672K exe) and prune the Mono-only directories, leaving the already-matching
  Windows payload alone. The folder was restored from Steam afterwards;
  see `docs/superpowers/plans/2026-09-18-linux-install-recovery.md`. The design conclusion the
  bullet supports still holds: both builds' files can coexist, and the IL2CPP inputs needed for
  interop generation are present without downloading a depot.
```

Adjust the final sentence to match what Task 1 actually found. If the restore did **not** work,
say so plainly instead — an unrestored install changes what §4.6's "full Linux smoke run" can
mean, and that is reported, not absorbed.

- [ ] **Step 2: Harden H1 in the Phase 0 plan**

Restructure H1 into two checkbox steps so the guard is *above* the command it guards — a document
written to stop a recurrence has to be safe read top to bottom, which is how the accident
happened. Replace everything from the existing `- [ ] **Download the Windows depot into a fresh
directory**` heading through the end of the retry paragraph with:

```markdown
**Before running steamcmd, check the target is not inside a Steam library.** This exact command
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
```

- [ ] **Step 3: Commit**

```bash
cd /home/oldmoldycake/Projects/jev_vampire_survivors
git add docs/superpowers/specs/2026-09-18-windows-support-and-pinned-picks-design.md docs/superpowers/plans/2026-09-18-windows-phase-0-spike.md
git commit -m "docs: record the overwritten Linux install and harden the Phase 0 download step

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019VzgtSAh31zbf8s8GCuyaE"
```

---

## Sequencing note

Task 1 Step 1 is a human step with a download behind it. Tasks 3 and 4 are repo work that does
not depend on it, **except** Task 3 Step 3 (the happy-path build), which needs the restored
install. A reasonable order when the download is slow: Task 0 → Task 3 Steps 1, 2, 4, 5, 6 →
Task 4 → then Task 1 → Task 2 → Task 3 Step 3 → Task 3 Steps 7, 8.

## Self-review

**Error coverage:** E1 → Task 1. E2 → Tasks 1 and 2. E3 → Task 4 Step 1. E4 → Task 4 Step 2.
E5 → Task 3. The dotnet non-error is recorded above with the evidence that rules it out.

**What this plan deliberately does not do:**

- It does not re-download `~/games/vs-windows`, which passed Phase 0 criterion 1 intact.
- It does not start Phases 1-3 of the Windows port, or the Phase 1 Python rewrite of the scripts
  that will eventually absorb Task 3's guard.
- It does not touch the brain, the Part A branch, or anything under `docs/superpowers/ledgers/`.
- It does not attempt to recover the Mono assemblies from anywhere other than Steam. They are
  poncle's shipped files; Steam is the only correct source.
