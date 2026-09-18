# SDD ledger — plan: docs/superpowers/plans/2026-09-17-jev-vs-brain.md

Spec: docs/superpowers/specs/2026-09-17-jev-vampire-survivors-design.md (read; binding authority)
Worktree: .claude/worktrees/jev-vs-impl, branch worktree-jev-vs-impl, base fa60389
Baseline: repo held only docs at base; no test suite to run.

## Pre-flight conflict scan (2026-09-18)

| Pair / task | Produces vs consumes | Finding |
|---|---|---|
| 1 ↔ 3 | protocol.move_reply lazily imports questions.DIRECTION_VECTORS; Task 1 writes a stub questions.py, Task 3 rewrites it with the same keys/vectors | consistent |
| 2 ↔ 3 | Task 2 appends Thresholds/DEFAULT_THRESHOLDS to the stub; digest imports Thresholds at runtime; Task 3 rewrite keeps fields and imports digest only under TYPE_CHECKING | consistent, no runtime cycle |
| 2 ↔ 4 | digest.digest_state / SectorSummary.pressure,gems,gem_count consumed by decide.fallback_direction | consistent |
| 3 ↔ 4 | questions.Ask(name,state,question,keys,instructions,labels), direction_question, options_question consumed by Decider | consistent |
| 4 ↔ 5 | decide.Decision (source, latency_ms, input_tokens, to_dict) consumed by Stats.record and server | consistent |
| 5 ↔ 6 | RunLog.start_run/tick/event/end_run/update_meta/active; Hub.publish/subscribe/unsubscribe/client_count/is_subscribed; Stats API consumed by server | consistent (update_meta defined in Task 5 code though absent from its Interfaces list) |
| 6 ↔ 7 | PluginServer.hub/stats/latest_decisions/recent_log/current_run/send_control/_record_decision consumed by dashboard and its tests | consistent (test calls private _record_decision; acceptable) |
| 6 ↔ 8 | PluginServer(config,decider,runlog,hub,stats).start()/port; make_app(server); run_dashboard(app,host,port) consumed by __main__ | consistent |
| 1 ↔ 8 | Config field names consumed by __main__ and server | consistent |
| 4 ↔ 9 | JevClient(model,timeout_s,max_retries); Decider.direction/pick used by live tests | consistent |
| conftest(2) ↔ 4 | FakeJev.ask returns JevResult(answers: dict[str, ChoicePick]) matching jev_client dataclasses | consistent |
| Task 1 self | tests vs code: decode/encode/move_reply/pick_reply/noop/control; config defaults/overrides/frozen | agrees |
| Task 2 self | bucket boundaries in tests match code (hp_bucket(5,0) -> critical; 3.9/4.0 -> far -> light) | agrees |
| Task 3 self | hp=20 -> critical; one touching enemy -> moderate; keys dedupe WHIP_3 | agrees |
| Task 4 self | fallback ordering (pressure rank, gem rank, gem count) matches tests | agrees |
| Task 5 self | Stats avg over jev calls only; Hub drop at maxsize; RunLog buffered pre-run ticks | agrees |
| Task 6 self | reused reply choice "stay" when no last direction; 4 event lines incl. game_over | agrees |
| Task 7 self | slow-client drop observed via is_subscribed after get | agrees |
| Task 8 self | build(Config) constructs a real JevClient without an API key in the test | RISK: the SDK may raise on construction when TYPESAFE_API_KEY is absent (spec 8: brain must run and fall back without a key) |
| Task 9 self | live tests skip without key | agrees |

Ruling: JevClient must not fail at construction when the API key is missing — construct the SDK client lazily on first ask() (or catch and store the constructor error and raise it from ask()), so build()/run() work without a key and every decision becomes a fallback as spec section 8 requires — carried into the Task 4 and Task 8 dispatches — cost if wrong: a few lines of rework in jev_client.py.
Ruling: commits made by implementers end with the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` per session attribution rules — cost if wrong: cosmetic.

## Task log
Task 1: dispatched (implementer haiku, BASE fa60389)
Task 1: review clean (spec ✅, approved). ⚠️ resolved by controller: 400/3000 ms reply budgets are plugin-side timeouts per spec §6 (brain's request_timeout_s=0.8 is the SDK call timeout); __main__.py is created in Task 8.
Task 1: minor (deferred): move_reply raises KeyError instead of ProtocolError for an unknown choice (protocol.py:130)
Task 1: minor (deferred): source: str not constrained to Literal["jev","fallback","reused"] (protocol.py:130,140)
Task 1: minor (deferred): redundant Path() wrap in load_config (config.py:81); no test for unparseable config.toml
Task 1: complete (commits fa60389..edad289, review clean)
Task 2: dispatched (implementer haiku, BASE edad289)
Task 2: review clean (spec ✅, approved). ⚠️ (raw scalars in Digest reaching Jev) resolved by controller: Task 3's question builders forward only word buckets; Task 3 reviewer asked to verify against the constraint.
Task 2: minor (deferred): inconsistent zero half_h guards (digest.py:28-29 vs :106), no test for half_h == 0
Task 2: minor (deferred): Digest.to_dict hand-rolled where dataclasses.asdict(self) suffices (digest.py:96-97)
Task 2: complete (commits edad289..0361dad, review clean)
Task 3: dispatched (implementer haiku, BASE 0361dad)
Task 3: review ❌ (Important, plan-mandated): options_question forwards build verbatim so raw level/minute ints reach Jev state (questions.py:178-180). ⚠️(1) "nowhere else" confirmed by controller: only questions.py defines questions/thresholds as of 409166e. ⚠️(2) resolved by the fix below (sanitised inside options_question).
Ruling: the plan's Task 3 text (build passed through, test fixture with level/minute ints) conflicts with spec §5 "Jev never sees numbers it has to reason about"; spec wins. options_question must build state["build"] = {"weapons": [...], "passives": [...], "run_phase": _minute_words(minute)} and drop level; tests updated to assert no int values in state["build"] — the plugin may keep sending level/minute since the brain sanitises — cost if wrong: Jev loses the player level as context for level-up picks (recoverable by adding a word bucket later).
Task 3: minor (deferred): DIRECTIONS[:-1] duplicates digest.SECTORS (questions.py:44-46)
Task 3: minor (deferred): no tests for unknown kind ValueError or blank description; arcana_select descriptions omit kind/is_new bits; frozen Ask has mutable containers
Task 3: fix round 1/5 started (resume implementer)
Task 3: fix round 1/5 (1 addressed, 0 open — build sanitised to weapons/passives/run_phase; commits 409166e..06ae75c)
Task 3: complete (commits 0361dad..06ae75c, review clean after 1 fix round)
Task 4: dispatched (implementer haiku, BASE 06ae75c) — carries ruling: JevClient constructs the SDK client lazily on first ask() so a missing TYPESAFE_API_KEY never fails construction
Task 4: review clean (spec ✅, approved). Reviewer verified typesafe_sdk 0.6.0 raises TypeSafeError at construction without a key, so the lazy-construction ruling is load-bearing.
Task 4: minor (deferred): a jev answer with a valid choice but empty/missing probabilities passes through unvalidated (decide.py _ask); assert used for control flow in fallback_direction; test-local import; Decision not frozen
Task 4: complete (commits 06ae75c..d0c518e, review clean)
Task 5: dispatched (implementer haiku, BASE d0c518e)
Task 5: review clean (spec ✅, approved). ⚠️ (call sites of RunLog root, mark_reused, publish) resolved by controller: Task 6 server and Task 8 build() wire them; checked at those reviews.
Task 5: minor (deferred): buffered pre-run records get flush-time timestamps (runlog.py:100-125); no tests for end_run without start, publish with no subscribers, same-second dir collision; _latency_sum is an init-able dataclass field; tick/event duplicate shape; collision suffix starts at -2
Task 5: complete (commits d0c518e..cfe0531, review clean)
Task 6: dispatched (implementer sonnet, BASE cfe0531)
Task 6: review ❌ (2 Important): (a) plan-mandated — character_select with empty options skips run-start (server.py:166-175); (b) asyncio.create_task results discarded, stop() never cancels in-flight tasks, task exceptions invisible (server.py:119,121,47-52).
Ruling on (a): keep the behaviour — an event with no options cannot start a game run (the plugin also never sends one), so opening a run log for it would create empty run directories; the spec's "character_select starts a run" is read as "a character_select that picks a character"; a code comment records this — cost if wrong: an unlogged run in a case that cannot occur with the shipped plugin.
Ruling on ⚠️ (reused ticks not published to hub): spec §10 does not list reused as a publish trigger; the counter surfaces on the next decision's stats message; deferred as minor.
Task 6: minor (deferred): reused branch publishes nothing; unknown event types not _note'd; connected set at TCP accept rather than on hello; assert in port property; no serialisation of concurrent _on_event tasks
Task 6: fix round 1/5 started (resume implementer) — finding (b) plus the comment for (a)
Task 6: fix round 1/5 (2 addressed, 0 open — task set + cancel on stop + exception logging; ruling comment; commits f0a101d..7dec685)
Task 6: complete (commits cfe0531..7dec685, review clean after 1 fix round)
Task 7: dispatched (implementer sonnet, BASE 7dec685)
Task 7: review ❌ (1 Important): non-dict JSON on /ws raises AttributeError and kills that socket's control channel (dashboard.py:53). ⚠️(1) confirmed as a real gap by controller: spec §10 wants a table of previous run summaries "from this session", but the snapshot carries no run history, so runs finished before connect never show — enters the fix loop. ⚠️(2) resolved: pickup dots stand for chests and other pickups (kind TREASURE is a pickup).
Ruling: add PluginServer.run_history (list of run-end summaries, appended in _on_event game_over) and include it in the snapshot as "runs"; the page renders them on snapshot — cost if wrong: a few lines across server.py/dashboard.py/index.html.
Task 7: minor (deferred): pump_task cancelled but never awaited; renderDecision interpolates labels/instructions into innerHTML unescaped; no onmessage case for "tick" (nothing publishes it today); direction indicator is a line not an arrow; bool() coercion of automation
Task 7: fix round 1/5 started (resume implementer)
Task 7: fix round 1/5 (2 addressed, 0 open — isinstance guard on control frames; run_history in snapshot; commits 79c0bb8..6087b5b)
Task 7: complete (commits 7dec685..6087b5b, review clean after 1 fix round)
Task 8: dispatched (implementer sonnet, BASE 6087b5b)
Task 8: review ❌ (1 Important, plan-mandated): JevClient.aclose() is never called at shutdown because run() has no handle to the client (__main__.py:36,54-55; decide.py:57-58).
Ruling: add a public read-only `jev` property to Decider and have run() call `await server.decider.jev.aclose()` after runner.cleanup(); build() keeps its (server, app) return type — cost if wrong: one extra property and one await.
Task 8: minor (deferred, plan-mandated): unhandled FileNotFoundError for --config missing file (__main__.py:61) and --replay dir without ticks.jsonl (fake_plugin.py:67); ConnectionRefusedError when the brain is not running (fake_plugin.py:40)
Task 8: fix round 1/5 started (resume implementer)
Task 8: fix round 1/5 (1 addressed, 0 open — Decider.jev property + aclose at shutdown; commits 496c4cd..d1e03c8)
Task 8: complete (commits 6087b5b..d1e03c8, review clean after 1 fix round)
Task 9: dispatched (implementer haiku, BASE d1e03c8)
Task 9: review clean (spec ✅, approved, no findings)
Task 9: complete (commits d1e03c8..9423620, review clean)
All tasks complete; final whole-branch review dispatched (fable) over fa60389..9423620
Final review (fable): ready WITH FIXES. Important: (1) summary.json / run-end message lack spec §9 jev/fallback counts and mean latency; (2) RunLog._pending unbounded and never cleared without start_run (F9-off and mid-run-restart scenarios); (3) fallback warning at tick rate vs spec §5 once per minute; (4) plan/spec design point for the plugin: reused replies vs "ignore older replies" can cost a tick of latency. Deferred-minor triage: all stay deferred except Task 5 buffered-record timestamps (fold into fix 2). All rulings judged sound; Task 7 ruling "sound but incomplete" (fix 1 completes it).
Ruling on (4): the plugin's Movement applies every `move` reply in arrival order, including a late reply whose request already timed out (a `jev` reply is always fresher information than an earlier `reused` one); the brain keeps answering overlapping ticks immediately with the last decision. Carried into the plugin plan's Task 3/4 dispatches — cost if wrong: one tick (250 ms) of movement latency in the worst case.
Ruling: fix wave also takes the reviewer's cheap hardening items (normalise build items to strings, echo option["index"], clear log/runs tables on snapshot, keyless-JevClient fallback test, Origin allowlist on /ws) and the spec housekeeping (§9 thresholds location, §10 tick message note, §4 source values) — cost if wrong: small extra diff to re-review.
Final fix wave dispatched (sonnet, FIX_BASE 9423620)
Final fix wave: re-review clean (9/9 addressed, no new breakage; commits 9423620..51c4ef5)
Brain plan complete: fa60389..51c4ef5, 14 commits, 74 offline tests passing, 3 live tests behind marker
