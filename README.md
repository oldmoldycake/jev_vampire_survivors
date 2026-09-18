# Jev plays Vampire Survivors

TypeSafe's Jev model picks the character, the stage, every level-up, and the walking
direction four times a second, in the real Steam game, with a live ops dashboard.

Design: `docs/superpowers/specs/2026-09-17-jev-vampire-survivors-design.md`.

## One-time setup

1. `curl -sSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 8.0` (installs to `~/.dotnet`)
2. `scripts/install_bepinex.sh`, then set the Steam launch option for Vampire Survivors to `./run_bepinex.sh %command%`
3. `scripts/deploy_mod.sh` (builds the plugin into `<game>/BepInEx/plugins/JevSurvivors/`)
4. `export TYPESAFE_API_KEY=...` in the shell that runs the brain

Or put `TYPESAFE_API_KEY=...` in a git-ignored `.env` at the repository root and start the brain with `cd brain && uv run --env-file ../.env jev-vs`.

## Play

```bash
cd brain && uv run jev-vs        # brain + dashboard at http://127.0.0.1:48232/
```

Then launch Vampire Survivors from Steam and touch nothing: the plugin continues the warning and landing screens, picks a character and stage through Jev, and plays. Do not click into the game window while a run is going: the game pauses when it loses focus, and the plugin resumes it, so a click may register as a menu press. F9 in the game, or PAUSE on the dashboard, hands control back to you; press again to resume. Resuming automation takes effect in-run or at the next page; a menu that was open when you paused needs one press from you.

Run logs land in `brain/runs/<timestamp>/` (`ticks.jsonl`, `events.jsonl`, `summary.json`).

## Tuning

- Questions and thresholds: `brain/jev_vs/questions.py` (the only file Jev's wording lives in).
- Brain ports, tick rate, model, timeouts: `brain/config.toml`.
- Plugin timing, entity caps, run count, hotkey: `<game>/BepInEx/config/dev.oldmoldycake.jevsurvivors.cfg`.

## Develop

- Brain tests: `cd brain && uv run pytest` (`uv run pytest -m live` calls the real API).
- Replay a run into the brain without the game: `uv run --project brain python scripts/fake_plugin.py --replay brain/runs/<stamp>`.
- Read game internals: `scripts/decompile.sh` writes C# to `decompiled/`.
- Plugin log: `<game>/BepInEx/LogOutput.log`.
- Launch or stop the game from a terminal and wait for log lines: `scripts/game_ctl.sh launch|wait-log PATTERN [TIMEOUT]|stop|status|log`.
