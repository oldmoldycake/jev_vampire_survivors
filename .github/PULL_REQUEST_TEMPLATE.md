## What this changes

<!-- A couple of sentences. Link the issue if there is one. -->

## What you tested it against

<!-- This project has real game-process and paid-API side effects, so "it compiles" isn't much
     signal on its own. Tick what applies and say what actually happened — how long the run was,
     what Jev did, which tests. -->

- [ ] A real run with the game
- [ ] A `scripts/fake_plugin.py` replay, or synthesized ticks, against a running brain
- [ ] `cd brain && uv run pytest`
- [ ] Built and deployed the plugin (`scripts/deploy_mod.sh`), no exceptions at boot
- [ ] Nothing yet — say what you'd like checked

Details:

## Checklist

- [ ] If this changes behavior that the README lists under [Known limitations](https://github.com/OldMoldyCake/jev_vampire_survivors#known-limitations) as unverified, I said how I verified it.
- [ ] Question wording and thresholds still live only in `brain/jev_vs/questions.py`.
- [ ] Behavior changes in the brain come with tests under `brain/tests/`.
- [ ] No API key, `.env` contents, or run-log dumps in the diff.
