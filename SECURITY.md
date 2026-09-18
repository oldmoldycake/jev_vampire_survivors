# Security

This project installs a mod into your Steam game, runs code inside the game process, opens two
unauthenticated sockets on loopback, and — if you give it a key — sends gameplay state to a
third-party API. None of that is a vulnerability; all of it is worth understanding before you
run it. That's the second half of this file. The first half is how to report something that
actually is a vulnerability.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting: the repository's **Security** tab →
**Report a vulnerability**, or go straight to
<https://github.com/OldMoldyCake/jev_vampire_survivors/security/advisories/new>. The report
stays private to the maintainer until there's a fix.

<!-- MAINTAINER: that link 404s until you turn the feature on. Repository Settings → Advanced
     Security (older UI: "Code security and analysis") → Private vulnerability reporting → Enable.
     Do it before you announce the repo, or the only reporting route in this file is broken.
     If you ever want an email route as well, add a dedicated address here — never a personal one. -->

Please don't open a public issue for something exploitable. There is no bounty and no response
SLA; this is one person's side project, so expect a reply in days rather than hours, and expect
"won't fix, documented instead" to be a real outcome for anything in the Security model section
below.

What helps: what the attacker needs to already have (local shell on the same machine? a browser
tab open? a malicious PR merged?), what they get out of it, and the smallest reproduction you
have. A proof of concept against a default `brain/config.toml` is worth more than a description.

## Supported versions

| Version | Supported |
| --- | --- |
| Latest `main` | Yes |
| Anything else | No |

This is at v0.1.0 and hobby-scale. There are no maintenance branches and no backport policy:
fixes land on `main`, and the answer to "is this fixed in my checkout" is "pull `main`". If
you're reporting against an older commit, re-pull first and check it still reproduces.

## Security model: what this software does to your machine

### It runs code inside the game process

The plugin in `mod/JevSurvivors` is a BepInEx 5 plugin. It installs [Harmony](https://harmony.pardeike.net/)
patches on the game's own methods (`VsCharacter.ProcessRawDirection`, `BaseUIPage.OnShowStart`,
`LevelUpPage.EnableLevelupOptions`, and others in `Patches.cs`) and is compiled against a
*publicized* copy of `VampireSurvivors.Runtime.dll` — `BepInEx.AssemblyPublicizer.MSBuild` rewrites
the game's private members as public so the plugin can read and call them by name. This is
ordinary Unity modding practice, and it also means the plugin is arbitrary code running with your
user's full privileges inside a process you launched from Steam. It can do anything your user
account can do; the game is just where it lives.

Installing this is a decision to trust this repository, the specific commit you built, and every
future commit you pull. Read `mod/JevSurvivors/` before you deploy it — it's five small files.

Once BepInEx is installed, the same applies to *anything* in `<game>/BepInEx/plugins/`, not just
this plugin. To back out: delete `<game>/BepInEx/plugins/JevSurvivors/` to remove this plugin, or
clear the Steam launch option (`./run_bepinex.sh %command%`) and the game starts with no BepInEx
at all.

### The BepInEx installer does not verify what it downloads

`scripts/install_bepinex.sh` fetches `BepInEx_linux_x64_<version>.zip` from the BepInEx GitHub
release page over HTTPS and unzips it directly into your Steam game folder, then makes
`run_bepinex.sh` executable and points its `executable_name` at `VampireSurvivors.exe`.

**It does not verify a checksum or a signature.** The only integrity guarantee is TLS plus
GitHub's release hosting — there is no pinned hash in the script, so a compromised or substituted
artifact would be installed without complaint. This is a known gap, stated here rather than
papered over. If that isn't good enough for you, skip the script: download the release yourself,
check it against the hashes BepInEx publishes, and unzip it into the game folder by hand — the
script does nothing else of substance. A PR that pins and verifies a SHA-256 (while still
allowing `BEPINEX_VERSION` to be overridden) would be welcome.

Two related notes, same trust model as any package install: `scripts/decompile.sh` will run
`dotnet tool install -g ilspycmd` from NuGet if `ilspycmd` isn't already on your `PATH`, and
`scripts/deploy_mod.sh` restores NuGet packages to build the plugin.

### Two unauthenticated listening sockets

Both are defined in `brain/config.toml` and both bind `127.0.0.1` by default:

- **127.0.0.1:48231 — plugin ↔ brain.** Newline-delimited JSON. No handshake, no authentication,
  no notion of which process is on the other end. Any local process can connect and feed the
  brain fabricated game state, or read the state the game is sending.
- **127.0.0.1:48232 — dashboard HTTP + WebSocket.** No authentication. The WebSocket is not
  read-only: a `{"type": "control", ...}` message pauses or resumes automation, so anything that
  can open that socket can take over or halt a run. The server does reject browser WebSocket
  upgrades whose `Origin` doesn't match the dashboard's own host — which stops a random page you
  have open in another tab from driving it — but a non-browser client that sends no `Origin`
  header at all is accepted by design, because that's how `scripts/fake_plugin.py` and other
  local tools connect.

Practical consequence: on a single-user desktop this is fine. On a shared machine, every other
local user can control the dashboard.

**Don't change either host to `0.0.0.0`, and don't expose the dashboard through a tunnel** —
ngrok, Cloudflare Tunnel, a reverse proxy, a remote-bound SSH forward. There is no login, no
token, and no rate limit to put in front of, and the dashboard accepts control commands. If you
want to watch a run from another machine, use an SSH *local* forward from that machine
(`ssh -L 48232:127.0.0.1:48232 you@gamebox`) so the authentication is SSH's, and the socket
itself stays on loopback at both ends.

### Game state leaves your machine when an API key is set

With `TYPESAFE_API_KEY` set, the brain calls TypeSafe's API (model `jev-latest`) over HTTPS up to
about four times a second. What it sends is the worded state digest plus the question and its
options: compass sectors, distance and HP buckets, and the in-game names of characters, stages,
weapons and upgrades. `brain/jev_vs/digest.py` and `brain/jev_vs/questions.py` are the complete
definition of what gets built and sent — raw coordinates never leave the brain, by design, and
nothing about your filesystem, environment or machine is included.

It is still gameplay data leaving your machine to a third party, and TypeSafe's terms and
retention policy govern it there, not this project. With no key set, the brain makes no outbound
calls at all: every decision comes from the local fallback heuristic.

### The API key and the run logs

- The key is read from the `TYPESAFE_API_KEY` environment variable, normally via a repo-root
  `.env` that `.gitignore` already excludes. Keep it there. Don't move it into `config.toml`,
  don't hardcode it, and don't paste it into an issue. If a key does leak, rotate it with
  TypeSafe first and clean up the paste second.
- Run logs under `brain/runs/` (git-ignored) contain the whole tick stream: the raw state the
  plugin sent, the digest built from it, and every model response with its probabilities and
  latency. Nothing in this repository writes your API key into them — but they are detailed, so
  skim a run before you attach it to an issue or hand it to anyone.

## Out of scope

- **Cheating, anti-cheat, and leaderboards.** This automates a single-player game on your own
  machine. How that interacts with anything the game reports or ranks is between you and poncle,
  and isn't something this project can or will address.
- **Bugs in Vampire Survivors itself.** Report those to [poncle](https://poncle.games/).
- **Bugs in BepInEx, Harmony, aiohttp, the TypeSafe SDK, or any other dependency.** Report those
  upstream. If a published advisory affects what this project ships or recommends by default, a
  normal issue here pointing it out is welcome.
- **The plugin breaking after a game update.** Expected, and documented under
  [Platform support](README.md#platform-support) — that's a regular issue, not a security report.
