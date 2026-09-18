# SDD ledger — plan: docs/superpowers/plans/2026-09-17-jev-vs-plugin.md

Spec: docs/superpowers/specs/2026-09-17-jev-vampire-survivors-design.md (read; binding authority)
Worktree: .claude/worktrees/jev-vs-impl, branch worktree-jev-vs-impl (continues after the brain plan), base 51c4ef5
Baseline: brain suite 74 passed at base; no plugin code yet.
User consent 2026-09-18: install BepInEx into the game folder; user sets the Steam launch option by hand; subagents may launch the game from the terminal for verification.

## Pre-flight conflict scan (2026-09-18)

| Pair / task | Produces vs consumes | Finding |
|---|---|---|
| 2 ↔ 3 | Plugin.cs config entries and SetAutomation; Transport(host, port, helloJson) with Start/Stop/Send/Request/Pump/Connected consumed by Plugin | consistent |
| 3 ↔ 4 | Transport.Request(JObject, float, Action<JObject>, Action) consumed by StateSampler with Movement.Apply/OnTimeout as callbacks | consistent |
| 4 ↔ 5 | Movement.Clear consumed by MenuDriver.OnRunStarted; Plugin.Update rewritten each task | consistent |
| 5 ↔ 6 | MenuDriver Ask/PickIndex/Event helpers, Handled set (replaced in Task 6), Patches.cs extended | consistent |
| 2 self | Probe reads publicized private _currentDirectionRaw; Input.GetKeyDown needs InputLegacyModule (referenced) | agrees, but the player-position probe needs a run started by hand (no menu driver yet) |
| 3 self | `??=` needs C# 8 (LangVersion latest); TcpClient/ConcurrentQueue exist in netstandard2.1 | agrees |
| 4 self | Stage._mainCamera + VampireSurvivors.Tools.CameraExtensions.OrthographicBounds; Pickup/Gem; EquipmentManager.ActiveEquipment; Equipment.Type/Level/IsMaxLevel | agrees (all verified in decompiled source) |
| 5 self | CharacterSelectionPage._characterItemUIs Dictionary<CharacterType, CharacterItemUI>; ShowCharacterInfo/SelectCharacter/ConfirmCharacter; StageSelectPage._spawned List<GameObject>, SetInfoPanel/SelectStage/ConfirmStage; WeaponSelectionPage._spawned List<WeaponSelectionItemUI> | agrees |
| 6 self | LevelUpPage.LevelUpItems + EnableLevelupOptions hook; LevelUpItemUI private fields; WeaponData.evoSynergy; Arcana/Treasure/Found/GameOver/Recap members; FindFirstObjectByType (Unity 6) | agrees |
| brain ↔ plugin | brain replies `move` for a tick id; reused replies answer overlapping ticks immediately; a late `jev` reply may arrive after its request timed out | RISK: Transport.Pump drops replies whose pending entry expired (see ruling below) |
| plan 1 | BepInEx 5.4.23.5 on Unity 6000 Mono/Linux unverified until Task 1 boots the game | spike; plan has the BepInEx 6 fallback |

Ruling (carried from the brain final review): Movement applies every `move` reply in arrival order, including late replies whose pending request already expired — Plugin.OnUnsolicited routes type "move" to Movement.Apply — carried into the Task 3 and Task 4 dispatches — cost if wrong: one tick of movement latency at worst.
Ruling: Task 2's acceptance is the "loaded" line, "probe: main menu shown", and a publicized private-member read at the main menu (ProbeMainMenuPatch also logs whether `__instance._StartButton` is non-null); the in-run player-position probe is verified when Task 5 starts runs automatically — cost if wrong: a publicizer problem surfaces one task later.
Ruling: subagents launch the game with `steam steam://rungameid/1794680` (Steam must be running), wait for the BepInEx log, and stop it with `pkill -f VampireSurvivors.exe`; they never leave the game running when they finish — cost if wrong: a stray game process the user closes by hand.

## Task log
Task 1: dispatched (implementer haiku, BASE 51c4ef5) — runs the install script; the user sets the Steam launch option afterwards
Task 1: install script run (commit 085e180); boot verified by the controller 2026-09-18 09:45: BepInEx 5.4.23.5 preloader + chainloader complete, "Detected Unity version: v6000.0.62f1", 0 plugins; spike PASS, BepInEx 5 is viable, no BepInEx 6 fallback needed.
Task 1: complete (commits 51c4ef5..085e180; no code review needed: shell script transcribed verbatim and its effect verified by the boot log)
Ruling: `pgrep/pkill -f VampireSurvivors.exe` match the caller's own shell (false positives seen); game process detection uses /proc/*/exe == the game binary. Task 2 adds `scripts/game_ctl.sh` (launch | wait-log | stop | status | log) as verification tooling; subagents run launch/wait in the background because foreground sleep is blocked — cost if wrong: one small extra script.
Task 2: dispatched (implementer sonnet, BASE 085e180)
Task 2: interim — plugin loads (log: "Loading [JevSurvivors 0.1.0]", "JevSurvivors 0.1.0 loaded; automation=True") but "probe: main menu shown" never fires: the boot stops on LandingScreenPage ("press any key"), so MainMenuPage.OnShowStart needs input. Implementer looped on relaunches (~17 min).
Ruling: Task 2's acceptance probe moves to the landing screen: Probe.cs adds a Harmony postfix on LandingScreenPage.Start logging "probe: landing screen shown; signal bus present={__instance._signalBus != null}" (publicized private field, no input needed); the main-menu probe stays for when a key is pressed; verification waits for the landing line — cost if wrong: none beyond one relaunch.
Task 2: review clean (spec ✅ incl. amendments, approved). Extra csproj references PauseSystem/PhaserPort/Zenject verified necessary by the reviewer (base-class chains and SignalBus). ⚠️ runtime log lines not re-verifiable by the reviewer: controller saw "JevSurvivors 0.1.0 loaded" in the live log and the implementer's report shows the landing probe line.
Task 2: minor (deferred): game_ctl.sh `log` lacks a file-exists guard; `wait-log` lacks an argument check; report misattributes the PauseSystem dependency
Task 2: complete (commits 085e180..8fbca63, review clean)
Ruling: Task 4's in-run verification (character moves, ticks flow) is deferred to Task 5's hands-off start, since no run can start without input until the menu driver exists; Task 4 acceptance = build, load, no exceptions at the landing screen, review — cost if wrong: a movement bug surfaces one task later.
Task 3: dispatched (implementer sonnet, BASE 8fbca63)
Task 3: review clean (spec ✅, approved). ⚠️ runtime evidence from the implementer's report only (connect, hello, control OFF/ON, link down, reconnect); accepted by controller.
Task 3: minor (deferred): Stop() does not unblock a thread parked in Connect()/backoff sleep (background threads, so harmless at exit); _thread never joined; _outbox could grow while disconnected if callers sent without checking Connected (Task 4/5 callers check Connected)
Task 3: complete (commits 8fbca63..1a6af11, review clean)
Task 4: dispatched (implementer sonnet, BASE 1a6af11) — carries ruling: OnUnsolicited routes type "move" to Movement.Apply
Task 4: review approved with 1 Important plan-mandated finding: BuildTick builds a JObject per on-screen entity before truncating to MaxEntities (GC churn scales with swarm size). ⚠️ in-run behaviour deferred to Task 5 as ruled.
Ruling: fix it now in a Task 4 fix round (collect (distanceSq, entity) pairs, sort, truncate, then build JSON for the survivors only); also amend spec §8's "Tick reply late: ignored if a newer reply exists" row to the arrival-order behaviour already ruled — cost if wrong: one small rebuild.
Task 4: minor (deferred): no recency guard on Movement.Apply (by ruling); gems/pickups getters share a mutable cache so loop order matters (a comment could pin it); BuildTick assumes RunActive preconditions
Task 4: fix round 1/5 started (resume implementer)
Task 4: fix round 1/5 (2 addressed, 0 open — JSON built only for nearest entities; spec §8 late-reply row; commits 5e3768d..8576f3b)
Task 4: minor (deferred): spec §2 names EnemyController under Objects.Characters.Enemies; the real namespace is Objects.Characters (doc fix for the final wave)
Task 4: complete (commits 1a6af11..8576f3b, review clean after 1 fix round)
Task 5: dispatched (implementer sonnet, BASE 8576f3b)
Task 5: BLOCKED at commit 482993b — boot shows VampireSurvivors.UI.WarningPage before the landing page; it needs AnyDown() after WaitDuration and no handler exists (plan defect: the boot flow was WarningPage -> LandingScreenPage -> MainMenu). Implementer's one attempt at a uinput synthetic keypress is out of bounds (outside the plan; harness flagged the follow-up); not to be repeated.
Ruling: MenuDriver gains OnWarning(WarningPage): wait until page._currentTime > page.WaitDuration (poll each frame, cap 10 s) plus MenuDelayS, then call the private page.Complete() (publicized), which hides the view and fires WarningShownSignal; Patches.cs gets a postfix on WarningPage.OnShowStart; typeof(WarningPage) joins Handled. Spec §7 step 1 to be amended in the final wave ("warning and landing pages are continued") — cost if wrong: one relaunch.
Task 5: fix round 1/5 started (resume implementer)
Task 5: fix round 1/5 (1 addressed — WarningPage continued in-process; commits 482993b..931dcb6). Hands-off start verified: WarningPage -> BackgroundPage -> landing -> MainMenuPage -> character select ANTONIO -> stage select FOREST -> MainGamePage -> run started. events.jsonl has character_select + stage_select; only 8 ticks because ArcanaMainSelectionPage opens at run start on this save (Task 6 scope).
Ruling: Task 5 is complete as scoped (run start); the ">= 40 ticks" evidence moves to Task 6's verification, which adds the arcana handler — cost if wrong: none, Task 6 verifies both.
Task 5: review dispatched over 8576f3b..931dcb6
Task 5: review approved with 1 Important: CharacterSelect/WeaponSelect/StageSelect do not re-check CanAutomate()/page after the Ask() wait (MenuDriver.cs ~172-256). ⚠️ plan text says MainGamePage does not override OnShowStart; it does but calls base, so the base dispatch still works (no change needed).
Task 5: minor (deferred): Handled set unused until Task 6; MainMenuPage.WaitAndReShow can re-fire the MainMenu coroutine in Adventure mode (no "already running" guard)
Task 5: fix round 2/5 started (resume implementer) — re-checks after the brain wait
Task 5: fix round 2/5 (1 addressed — re-check guards after the brain wait in three coroutines; commits 931dcb6..31cef11)
Task 5: complete (commits 8576f3b..31cef11, review clean after 2 fix rounds)
Ruling: Task 6's live verification is bounded to ~15 minutes: arcana handled, >= 40 ticks, >= 1 level-up pick within 4 min are required; the game-over -> recap -> main menu -> second run path is verified only if a game over occurs within a 12-minute budget (runs end by death, which fallback steering may delay), otherwise it is reported unverified and covered by Task 7's acceptance run — cost if wrong: an end-of-run bug found later.
Task 6: dispatched (implementer sonnet, BASE 31cef11)
Task 6: interim (user observed the game stuck on a treasure chest; log confirms OpenTreasurePage with no handler progress; PausePage cleared only by the 10 s safety net; safety net nudging BackgroundPage/MenuBannerPage).
Ruling: Treasure coroutine must press Open itself (page.OpenTreasure()), skip while allowed, then ClaimTreasure() when DoneButton is active, 120 s cap; a PausePage handler calls ReturnToGame() after MenuDelayS while automation is on (typeof(PausePage) in Handled, PausePatch on its OnShowStart); the safety net ignores BackgroundPage and MenuBannerPage — plan defects (§7 never listed pause or the chest's Open press) — cost if wrong: one relaunch.
Task 6: DONE_WITH_CONCERNS at b42b227 — live: arcana pick, 9 level-ups, pause resumed, 862 ticks with all compass choices, no unknown-page nudges. Not exercised live: treasure (no chest appeared), game over (run healthy at 12-min budget; summary.json aborted by stop). BepInEx config file is named dev.oldmoldycake.jevsurvivors.cfg (by GUID), not JevSurvivors.cfg — README (Task 7) must say so.
Task 6: review dispatched over 31cef11..b42b227
Task 6: review ❌ (2 Important): (1) GameOver reads page._stageComplete synchronously but the game sets it ~1 s later in OnIntroEnded (stale/default value in every summary); (2) plan-mandated — CharacterFound's second wait lacks the CanAutomate()/page re-check. ⚠️ noted: OpenTreasurePage and MainGamePage do override OnShowStart but call base, so base-postfix dispatch fires once (brief text wrong, code right).
Task 6: minor (deferred): ReadKills relies on MainGamePage staying active under the game-over overlay (unverified live); treasure deadline computed before the 0.5 s wait; GameOver's summary/event path intentionally ungated by automation (needs a comment)
Task 6: fix round 1/5 started (resume implementer)
Task 6: fix round 1/5 (2 addressed — stage_complete read after the game computes it; CharacterFound re-check; commits b42b227..5d894ea)
Task 6: complete (commits 31cef11..5d894ea, review clean after 1 fix round; treasure and game-over paths verified by code review only, to be exercised in Task 7's acceptance run)
Task 7: dispatched (implementer haiku, BASE 5d894ea) — README plus doc corrections; acceptance run gated on the user's API key
Task 7: acceptance run dispatched (sonnet) — brain started with --env-file ../.env (user's key; never printed), full run to game over, dashboard checks over the WebSocket, F9 not testable by an agent (user may try it)
Task 7 (docs): review — all mandated items ✅. Reviewer's "Important" (commit trailer should name its own model) is wrong: Ruling: the trailer `Co-Authored-By: Claude Fable 5.1` is mandated by this session's attribution rule; parked — cost if wrong: cosmetic.
Task 7 (docs): minor (deferred): spec §6 lists MainGamePage/OpenTreasurePage alongside pages with their own OnShowStart postfix without saying they are dispatched from the base postfix
Task 7 (docs): complete (commits 5d894ea..4fa0bc2, review clean after ruling); acceptance run in progress
Task 7: acceptance run PASS (controller-run 2026-09-18 12:10-12:12, brain with the user's key): warning -> landing -> main menu -> character select GERMANA (brain) -> stage select FOSCARI -> run started -> arcana T07_IRON_BLUE -> 4 level-ups (brain) -> game over {seconds 77, level 5, kills 352, stage_complete false} -> recap dismissed -> main menu -> CharacterSelectionPage again; 0 unknown pages, 0 failed lines; ticks 273 all source=jev, 0 fallback; summary.json jev_calls 280, reused 26, avg latency 204 ms, cost $0.0089. Dashboard pause/resume round-trip verified by the earlier agent. Not exercised: treasure (no chest), pause (no focus loss), F9 (needs a human).
Task 7: complete (commits 5d894ea..4fa0bc2 docs; acceptance evidence in this ledger)
All plugin tasks complete; final whole-branch review over 51c4ef5..4fa0bc2 (fable)
Final review (fable): ready WITH FIXES. Important: (1) level-up `level` always 0 (LevelUpItemUI._currentLevel is never written by the game; use _levelData/_data.level); (2) revivable death is quit instead of revived (GameOverPage._hasRevives / Revive()); (3) stage modifiers inherited from the save instead of forced off; (4) Application.version read on the transport thread; (5) spec §6 contradicts itself on ticks while automation is off. Minors 6-15 listed in the review; deferred-minor triage: all leave deferred or already resolved; all rulings judged sound.
Ruling: revive when the game offers it — after the 2 s wait, if page._hasRevives call page.Revive() and return without counting or reporting the run; spec §7 step 6 records it — cost if wrong: a run continues past a death the human would have accepted.
Ruling: stage modifiers are forced off before ConfirmStage (tick boxes InitialSet(false) or the Config.Selected* fields) — cost if wrong: none; matches spec §7.
Ruling: spec §6 kill-switch bullet amended to "ticks stop while automation is off" (implementation and plan already do this; avoids Jev spend while a human plays) — cost if wrong: the dashboard freezes while the human plays.
Ruling: the fix wave also takes cheap minors 6 (Transport comment), 7 (throttle "brain link down"), 8 (_nudged reset and null-key pruning), 10 (RunsStarted counted in OnRunStarted), 11 (README resume note), 12 (Camera.main fallback), 13 (spec §12/§6 drift); 9, 14, 15 stay deferred — cost if wrong: a larger diff to re-review.
Final fix wave dispatched (sonnet, FIX_BASE 4fa0bc2)
Final fix wave: re-review clean (12/12 addressed; two Low residuals: double-null camera fallback warning unthrottled; automation toggled off during the 2 s game-over wait skips a possible revive — both deferred; commits 4fa0bc2..b60a86f)
Plugin plan complete: 51c4ef5..b60a86f, 11 commits. Not exercised live: treasure chest, 30-minute stage clear, revivable death, F9 by hand.
