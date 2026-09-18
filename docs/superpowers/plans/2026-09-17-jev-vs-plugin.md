# Jev Vampire Survivors Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the BepInEx plugin that lets the Python brain play the real Vampire Survivors: it streams raw game state, applies movement, and drives every menu from boot to game over and back, with safe defaults whenever the brain is silent.

**Architecture:** A C# BepInEx 5 plugin for the native Linux Mono build. A background thread owns a TCP link to the brain (newline JSON, request ids, timeouts). On the Unity main thread, a sampler sends a `tick` at a fixed rate, a Harmony prefix on the player's `ProcessRawDirection` overwrites the raw input direction with the brain's vector, and a menu driver made of Harmony postfixes on page `OnShowStart` methods reads each page's options with the game's own classes and applies the brain's pick through the page's own methods. The plugin holds no strategy.

**Tech Stack:** .NET SDK 8 (installed user-locally at `~/.dotnet`), C# targeting `netstandard2.1`, BepInEx 5.4.23.5 Linux x64, HarmonyX (`0Harmony.dll` shipped with BepInEx), `BepInEx.AssemblyPublicizer.MSBuild` 0.4.3, Newtonsoft.Json (shipped with the game), Unity 6000.0.62f1 assemblies from the game's `Managed` folder, ilspycmd 9.1 for decompiling.

**Spec:** `docs/superpowers/specs/2026-09-17-jev-vampire-survivors-design.md` (sections 2, 3, 4, 6, 7, 8, 11)

**Companion plan:** `docs/superpowers/plans/2026-09-17-jev-vs-brain.md`. Tasks 3 onward need a running brain (`cd brain && uv run jev-vs`).

## Global Constraints

- Game: Vampire Survivors 1.16.107, Unity 6000.0.62f1, native Linux Mono build at `~/.local/share/Steam/steamapps/common/Vampire Survivors`. Game logic assembly: `VampireSurvivors_Data/Managed/VampireSurvivors.Runtime.dll`.
- BepInEx `5.4.23.5`, asset `BepInEx_linux_x64_5.4.23.5.zip`. Steam launch option: `./run_bepinex.sh %command%`.
- Plugin id `dev.oldmoldycake.jevsurvivors`, name `JevSurvivors`, version `0.1.0`.
- Protocol (spec section 4): plugin sends `hello`, `tick`, `event`; brain replies `move`, `pick`, `noop`; brain may send `control`. Every request carries an integer `id`; ticks wait `ReplyTimeoutMs` (400), menu events wait `MenuReplyTimeoutMs` (3000). On timeout: keep last direction (zeroed after 1 s of silence) or take option 0.
- Never block the Unity main thread on the network; never touch Unity objects off the main thread; every Harmony postfix catches its own exceptions so the game method still completes.
- Private game members are reached through the publicizer, not reflection.
- Alias the player class everywhere: `using VsCharacter = VampireSurvivors.Objects.Characters.CharacterController;` because `UnityEngine.CharacterController` collides with it.
- Namespaces (verified from the decompiled source): enums `WeaponType, ItemType, CharacterType, StageType, ArcanaType, EnemyType` in `VampireSurvivors.Data`; `GM, GameManager, LevelUpFactory` in `VampireSurvivors.Framework`; `Stage, Equipment, EquipmentManager, PlayerOptions` in `VampireSurvivors.Objects`; `CharacterController, EnemyController` in `VampireSurvivors.Objects.Characters`; `Gem` in `VampireSurvivors.Objects.Items`; `Pickup` in `VampireSurvivors.Objects.Pickups`; `CameraExtensions` in `VampireSurvivors.Tools`; `BaseUIPage, LandingScreenPage, MainMenuPage, CharacterSelectionPage, CharacterItemUI, StageSelectPage, StageItemUI, WeaponSelectionItemUI, LevelUpPage, ArcanaMainSelectionPage, ArcanaCardUI, OpenTreasurePage, ItemFoundPage, CharacterFoundPage, GameOverPage, RecapPage` in `VampireSurvivors.UI`; `LevelUpItemUI, WeaponSelectionPage, MainGamePage` in `VampireSurvivors`; `WeaponData` in `VampireSurvivors.Data.Weapons`; `ItemData` in `VampireSurvivors.Data.Items`; `StageData` in `VampireSurvivors.Data.Stage`; `CharacterData` in `VampireSurvivors.Data.Characters`; `ArcanaData` in `VampireSurvivors.Data`.
- There are no unit tests for Unity code. Each task's test is: it builds, it deploys, and the BepInEx log (`<game>/BepInEx/LogOutput.log`) and the brain log show the exact lines listed. The game must be restarted after every deploy.
- Commit after every task: `feat(mod): ...`.

---

## File Structure

```
scripts/
  install_bepinex.sh          downloads BepInEx into the game folder, sets executable_name
  deploy_mod.sh               dotnet build + copy DLL into BepInEx/plugins/JevSurvivors/
  decompile.sh                ilspycmd VampireSurvivors.Runtime.dll -> decompiled/ (git-ignored)
mod/
  Directory.Build.props       GameDir, ManagedDir, BepInExDir
  JevSurvivors/
    JevSurvivors.csproj        netstandard2.1, publicized game reference, Unity refs
    Plugin.cs                  BepInPlugin entry: config, Harmony, per-frame Update, hotkey, control
    Probe.cs                   spike diagnostics (Task 2 only, deleted in Task 5)
    Transport.cs               TCP client thread, NDJSON, request ids, timeouts, reconnect
    StateSampler.cs            builds and sends tick JSON from GM.Core
    Movement.cs                latest move vector + Harmony prefix on ProcessRawDirection
    MenuDriver.cs              coroutines that read pages, ask the brain, apply picks; safety net
    Patches.cs                 Harmony postfixes that hand pages to MenuDriver
README.md                     setup and run instructions (Task 7)
```

---

### Task 1: Install BepInEx and prove the game boots with it

**Files:**
- Create: `scripts/install_bepinex.sh`

**Interfaces:**
- Produces: BepInEx installed in the game folder; `run_bepinex.sh` executable with `executable_name="VampireSurvivors.exe"`; the Steam launch option set by the user.

- [ ] **Step 1: Write the install script**

```bash
#!/usr/bin/env bash
# Installs BepInEx 5 (Linux x64) into the Vampire Survivors folder. Safe to re-run.
set -euo pipefail
GAME_DIR="${GAME_DIR:-$HOME/.local/share/Steam/steamapps/common/Vampire Survivors}"
VER="${BEPINEX_VERSION:-5.4.23.5}"
URL="https://github.com/BepInEx/BepInEx/releases/download/v${VER}/BepInEx_linux_x64_${VER}.zip"

[ -d "$GAME_DIR" ] || { echo "game dir not found: $GAME_DIR" >&2; exit 1; }
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
echo "downloading $URL"
curl -sSL "$URL" -o "$tmp/bepinex.zip"
unzip -o -q "$tmp/bepinex.zip" -d "$GAME_DIR"
chmod u+x "$GAME_DIR/run_bepinex.sh"
sed -i 's/^executable_name=.*/executable_name="VampireSurvivors.exe"/' "$GAME_DIR/run_bepinex.sh"
grep -q 'executable_name="VampireSurvivors.exe"' "$GAME_DIR/run_bepinex.sh"
mkdir -p "$GAME_DIR/BepInEx/plugins"
echo "BepInEx $VER installed in: $GAME_DIR"
echo
echo "NOW: Steam -> Vampire Survivors -> Properties -> Launch Options, set exactly:"
echo '    ./run_bepinex.sh %command%'
```

- [ ] **Step 2: Run it**

Run: `chmod +x scripts/install_bepinex.sh && scripts/install_bepinex.sh`
Expected: prints `BepInEx 5.4.23.5 installed in: ...` and the launch-option reminder. `ls "$HOME/.local/share/Steam/steamapps/common/Vampire Survivors"` now shows `BepInEx/`, `doorstop_libs/`, `run_bepinex.sh`, `libdoorstop_x64.so`.

- [ ] **Step 3: Set the Steam launch option and boot the game**

In Steam: right-click Vampire Survivors, Properties, General, Launch Options: `./run_bepinex.sh %command%`. Launch the game, wait for the main menu, quit.

Run: `grep -E "BepInEx|Chainloader|Unity|Running under" "$HOME/.local/share/Steam/steamapps/common/Vampire Survivors/BepInEx/LogOutput.log" | head -20`
Expected lines include:
```
[Message:   BepInEx] BepInEx 5.4.23.5 - VampireSurvivors
[Info   :   BepInEx] Running under Unity v6000.0.62f1
[Message:   BepInEx] Chainloader ready
[Message:   BepInEx] Chainloader started
```

If `LogOutput.log` is missing, BepInEx did not load: check that the launch option is set and that `run_bepinex.sh` is executable. If the game crashes at boot, edit `BepInEx/config/BepInEx.cfg`, set `[Preloader.Entrypoint] Type = Camera`, retry. If it still fails, install `BepInEx-Unity.Mono-linux-x64-6.0.0-pre.2.zip` from the BepInEx 6 pre-release instead (same script with `BEPINEX_VERSION` logic replaced by that asset name) and note the change in `Directory.Build.props` (`BepInExDir/core` still holds `BepInEx.Core.dll` and `0Harmony.dll`; reference `BepInEx.Core` and `BepInEx.Unity.Mono` instead of `BepInEx`).

- [ ] **Step 4: Commit**

```bash
git add scripts/install_bepinex.sh
git commit -m "feat(mod): script to install BepInEx into the game folder"
```

---

### Task 2: Plugin scaffold with a diagnostics probe

**Files:**
- Create: `mod/Directory.Build.props`
- Create: `mod/JevSurvivors/JevSurvivors.csproj`
- Create: `mod/JevSurvivors/Plugin.cs`
- Create: `mod/JevSurvivors/Probe.cs`
- Create: `scripts/deploy_mod.sh`
- Create: `scripts/decompile.sh`

**Interfaces:**
- Produces: `Plugin` (BaseUnityPlugin) with static `Instance`, `Log`, `Automation`, config entries `Host, Port, TickHz, ReplyTimeoutMs, MenuReplyTimeoutMs, MenuDelayS, UnknownPageTimeoutS, MaxEntities, AutoplayOnBoot, MaxRuns, PauseBetweenRunsS, ToggleKey`, and `SetAutomation(bool on, string why)`.
- Consumes: BepInEx from Task 1.

- [ ] **Step 1: Write the build props and project file**

`mod/Directory.Build.props`:

```xml
<Project>
  <PropertyGroup>
    <GameDir Condition="'$(GameDir)' == ''">$(HOME)/.local/share/Steam/steamapps/common/Vampire Survivors</GameDir>
    <ManagedDir>$(GameDir)/VampireSurvivors_Data/Managed</ManagedDir>
    <BepInExDir>$(GameDir)/BepInEx</BepInExDir>
  </PropertyGroup>
</Project>
```

`mod/JevSurvivors/JevSurvivors.csproj`:

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>netstandard2.1</TargetFramework>
    <AssemblyName>JevSurvivors</AssemblyName>
    <RootNamespace>JevSurvivors</RootNamespace>
    <Version>0.1.0</Version>
    <LangVersion>latest</LangVersion>
    <Nullable>disable</Nullable>
    <ImplicitUsings>disable</ImplicitUsings>
    <CopyLocalLockFileAssemblies>false</CopyLocalLockFileAssemblies>
    <ProduceReferenceAssembly>false</ProduceReferenceAssembly>
    <DebugType>portable</DebugType>
    <NoWarn>$(NoWarn);MSB3277;CS0618;CS0649</NoWarn>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="BepInEx.AssemblyPublicizer.MSBuild" Version="0.4.3" PrivateAssets="all" />
  </ItemGroup>

  <ItemGroup>
    <Reference Include="BepInEx" Private="false"><HintPath>$(BepInExDir)/core/BepInEx.dll</HintPath></Reference>
    <Reference Include="0Harmony" Private="false"><HintPath>$(BepInExDir)/core/0Harmony.dll</HintPath></Reference>
    <Reference Include="VampireSurvivors.Runtime" Private="false" Publicize="true"><HintPath>$(ManagedDir)/VampireSurvivors.Runtime.dll</HintPath></Reference>
    <Reference Include="UnityEngine" Private="false"><HintPath>$(ManagedDir)/UnityEngine.dll</HintPath></Reference>
    <Reference Include="UnityEngine.CoreModule" Private="false"><HintPath>$(ManagedDir)/UnityEngine.CoreModule.dll</HintPath></Reference>
    <Reference Include="UnityEngine.InputLegacyModule" Private="false"><HintPath>$(ManagedDir)/UnityEngine.InputLegacyModule.dll</HintPath></Reference>
    <Reference Include="UnityEngine.UI" Private="false"><HintPath>$(ManagedDir)/UnityEngine.UI.dll</HintPath></Reference>
    <Reference Include="Unity.TextMeshPro" Private="false"><HintPath>$(ManagedDir)/Unity.TextMeshPro.dll</HintPath></Reference>
    <Reference Include="Newtonsoft.Json" Private="false"><HintPath>$(ManagedDir)/Newtonsoft.Json.dll</HintPath></Reference>
  </ItemGroup>
</Project>
```

- [ ] **Step 2: Write Plugin.cs and Probe.cs**

`mod/JevSurvivors/Plugin.cs`:

```csharp
using BepInEx;
using BepInEx.Configuration;
using BepInEx.Logging;
using HarmonyLib;
using UnityEngine;

namespace JevSurvivors
{
    [BepInPlugin(Id, Name, Version)]
    public class Plugin : BaseUnityPlugin
    {
        public const string Id = "dev.oldmoldycake.jevsurvivors";
        public const string Name = "JevSurvivors";
        public const string Version = "0.1.0";

        public static Plugin Instance { get; private set; }
        public static ManualLogSource Log { get; private set; }
        public static bool Automation { get; private set; }

        public static ConfigEntry<string> Host;
        public static ConfigEntry<int> Port;
        public static ConfigEntry<float> TickHz;
        public static ConfigEntry<int> ReplyTimeoutMs;
        public static ConfigEntry<int> MenuReplyTimeoutMs;
        public static ConfigEntry<float> MenuDelayS;
        public static ConfigEntry<float> UnknownPageTimeoutS;
        public static ConfigEntry<int> MaxEntities;
        public static ConfigEntry<bool> AutoplayOnBoot;
        public static ConfigEntry<int> MaxRuns;
        public static ConfigEntry<float> PauseBetweenRunsS;
        public static ConfigEntry<KeyCode> ToggleKey;

        private Harmony _harmony;

        private void Awake()
        {
            Instance = this;
            Log = Logger;

            Host = Config.Bind("Brain", "Host", "127.0.0.1", "Brain TCP host");
            Port = Config.Bind("Brain", "Port", 48231, "Brain TCP port");
            TickHz = Config.Bind("Timing", "TickHz", 4f, "State samples per second while a run is active");
            ReplyTimeoutMs = Config.Bind("Timing", "ReplyTimeoutMs", 400, "How long a tick waits for a move reply");
            MenuReplyTimeoutMs = Config.Bind("Timing", "MenuReplyTimeoutMs", 3000, "How long a menu event waits for a pick reply");
            MenuDelayS = Config.Bind("Timing", "MenuDelayS", 1.0f, "Seconds to wait after a page shows before reading it");
            UnknownPageTimeoutS = Config.Bind("Timing", "UnknownPageTimeoutS", 10f, "Seconds an unhandled page may stay open before Enter is pressed for it");
            MaxEntities = Config.Bind("Limits", "MaxEntities", 200, "Max enemies, gems, and pickups per tick, nearest first");
            AutoplayOnBoot = Config.Bind("Runs", "AutoplayOnBoot", true, "Start automating as soon as the game boots");
            MaxRuns = Config.Bind("Runs", "MaxRuns", 0, "Stop starting runs after this many; 0 = unlimited");
            PauseBetweenRunsS = Config.Bind("Runs", "PauseBetweenRunsS", 3f, "Seconds to idle on the main menu between runs");
            ToggleKey = Config.Bind("Hotkeys", "ToggleKey", KeyCode.F9, "Toggle automation on and off");

            Automation = AutoplayOnBoot.Value;
            _harmony = new Harmony(Id);
            _harmony.PatchAll(typeof(Plugin).Assembly);
            Log.LogInfo($"{Name} {Version} loaded; automation={Automation}");
        }

        private void Update()
        {
            if (Input.GetKeyDown(ToggleKey.Value)) SetAutomation(!Automation, "hotkey");
            Probe.Update();
        }

        public void SetAutomation(bool on, string why)
        {
            Automation = on;
            Log.LogInfo($"automation {(on ? "ON" : "OFF")} ({why})");
        }

        private void OnDestroy()
        {
            _harmony?.UnpatchSelf();
        }
    }
}
```

`mod/JevSurvivors/Probe.cs`:

```csharp
using HarmonyLib;
using UnityEngine;
using VampireSurvivors.Framework;
using VampireSurvivors.UI;

namespace JevSurvivors
{
    /// <summary>Spike-only diagnostics proving the publicizer, Harmony, and GM.Core access work. Deleted in Task 5.</summary>
    internal static class Probe
    {
        private static float _next;

        public static void Update()
        {
            if (Time.realtimeSinceStartup < _next) return;
            _next = Time.realtimeSinceStartup + 1f;
            var gm = GM.Core;
            if (gm == null || gm.Player == null || gm.Stage == null) return;
            var p = gm.Player;
            Vector3 pos = p.transform.position;
            Plugin.Log.LogInfo(
                $"probe: player at ({pos.x:F1},{pos.y:F1}) hp {p.CurrentHealth():F0}/{p.MaxHp():F0} lvl {p.Level} " +
                $"minute {gm.Stage.CurrentMinute} rawDir {p._currentDirectionRaw} enemiesOnScreen {gm.Stage.GetAllEnemiesInScreenBounds().Count}");
        }
    }

    [HarmonyPatch(typeof(MainMenuPage), "OnShowStart")]
    internal static class ProbeMainMenuPatch
    {
        private static void Postfix(MainMenuPage __instance)
        {
            Plugin.Log.LogInfo("probe: main menu shown");
        }
    }
}
```

- [ ] **Step 3: Write the deploy and decompile scripts**

`scripts/deploy_mod.sh`:

```bash
#!/usr/bin/env bash
# Builds the plugin and copies it into the game's BepInEx/plugins folder. Restart the game afterwards.
set -euo pipefail
cd "$(dirname "$0")/../mod/JevSurvivors"
export PATH="$HOME/.dotnet:$PATH"
export DOTNET_CLI_TELEMETRY_OPTOUT=1
GAME_DIR="${GAME_DIR:-$HOME/.local/share/Steam/steamapps/common/Vampire Survivors}"

command -v dotnet >/dev/null || {
  echo "dotnet SDK not found. Install user-locally with:" >&2
  echo '  curl -sSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 8.0' >&2
  exit 1
}
[ -f "$GAME_DIR/BepInEx/core/BepInEx.dll" ] || { echo "BepInEx not installed; run scripts/install_bepinex.sh first" >&2; exit 1; }

dotnet build -c Release "-p:GameDir=$GAME_DIR" "$@"
dest="$GAME_DIR/BepInEx/plugins/JevSurvivors"
mkdir -p "$dest"
cp bin/Release/netstandard2.1/JevSurvivors.dll "$dest/"
echo "deployed $dest/JevSurvivors.dll"
```

`scripts/decompile.sh`:

```bash
#!/usr/bin/env bash
# Decompiles the game's logic assembly into ./decompiled (git-ignored) for reading method bodies.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.dotnet:$HOME/.dotnet/tools:$PATH"
export DOTNET_CLI_TELEMETRY_OPTOUT=1
GAME_DIR="${GAME_DIR:-$HOME/.local/share/Steam/steamapps/common/Vampire Survivors}"
M="$GAME_DIR/VampireSurvivors_Data/Managed"
command -v ilspycmd >/dev/null || dotnet tool install -g ilspycmd --version 9.1.0.7988
rm -rf decompiled && mkdir -p decompiled
ilspycmd "$M/VampireSurvivors.Runtime.dll" -p -o decompiled -r "$M"
echo "decompiled to ./decompiled ($(find decompiled -name '*.cs' | wc -l) files)"
```

- [ ] **Step 4: Build and deploy**

Run: `chmod +x scripts/deploy_mod.sh scripts/decompile.sh && scripts/deploy_mod.sh`
Expected: `Build succeeded.` with 0 errors and the final `deployed .../BepInEx/plugins/JevSurvivors/JevSurvivors.dll`. If the publicizer step fails with a NuGet restore error, run `~/.dotnet/dotnet nuget locals all --clear` and retry. If the build errors on `Unity.TextMeshPro`, confirm the file name with `ls "$GAME_DIR/VampireSurvivors_Data/Managed" | grep -i textmesh` and fix the HintPath.

- [ ] **Step 5: Boot the game, start any run by hand, then quit; check the log**

Run: `grep -E "JevSurvivors|probe:" "$HOME/.local/share/Steam/steamapps/common/Vampire Survivors/BepInEx/LogOutput.log" | head -20`
Expected:
```
[Info   :   BepInEx] Loading [JevSurvivors 0.1.0]
[Info   :JevSurvivors] JevSurvivors 0.1.0 loaded; automation=True
[Info   :JevSurvivors] probe: main menu shown
[Info   :JevSurvivors] probe: player at (12.3,-4.0) hp 120/120 lvl 1 minute 0 rawDir (0.0, 0.0) enemiesOnScreen 7
```
The `probe: player` line proves the publicized private field `_currentDirectionRaw`, `GM.Core`, and `Stage.GetAllEnemiesInScreenBounds` all work at runtime. If `Loading [JevSurvivors` appears but the loaded line does not, look for a `TypeLoadException` just after it: that means a wrong target framework; change `TargetFramework` to `net472` in the csproj, rebuild, and redeploy. Press F9 during the run and confirm `automation OFF (hotkey)` is logged.

- [ ] **Step 6: Commit**

```bash
git add mod scripts/deploy_mod.sh scripts/decompile.sh
git commit -m "feat(mod): BepInEx plugin scaffold with config, Harmony, and diagnostics probe"
```

---

### Task 3: Transport to the brain

**Files:**
- Create: `mod/JevSurvivors/Transport.cs`
- Modify: `mod/JevSurvivors/Plugin.cs`

**Interfaces:**
- Produces: `Transport(string host, int port, Func<string> helloJson)` with `Start()`, `Stop()`, `bool Connected`, `Send(JObject msg)`, `long Request(JObject msg, float timeoutS, Action<JObject> onReply, Action onTimeout)` (assigns the `id`), `Pump(Action<JObject> onUnsolicited)` to be called every frame on the main thread.
- Produces on `Plugin`: `internal Transport Transport`, unsolicited `control` handling.
- Consumes: brain server from the brain plan.

- [ ] **Step 1: Write Transport.cs**

```csharp
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace JevSurvivors
{
    /// <summary>
    /// Newline-delimited JSON over TCP on a background thread. The main thread only touches
    /// Send/Request/Pump. Replies are matched to requests by id; late replies are dropped.
    /// </summary>
    public sealed class Transport
    {
        private sealed class Pending
        {
            public float Deadline;
            public Action<JObject> OnReply;
            public Action OnTimeout;
        }

        private readonly string _host;
        private readonly int _port;
        private readonly Func<string> _helloJson;
        private readonly ConcurrentQueue<string> _outbox = new ConcurrentQueue<string>();
        private readonly ConcurrentQueue<JObject> _inbox = new ConcurrentQueue<JObject>();
        private readonly Dictionary<long, Pending> _pending = new Dictionary<long, Pending>();
        private Thread _thread;
        private volatile bool _running;
        private volatile bool _connected;
        private long _nextId;

        public bool Connected => _connected;

        public Transport(string host, int port, Func<string> helloJson)
        {
            _host = host;
            _port = port;
            _helloJson = helloJson;
        }

        public void Start()
        {
            _running = true;
            _thread = new Thread(Loop) { IsBackground = true, Name = "JevSurvivors.Transport" };
            _thread.Start();
        }

        public void Stop()
        {
            _running = false;
        }

        public void Send(JObject msg)
        {
            _outbox.Enqueue(msg.ToString(Formatting.None));
        }

        public long Request(JObject msg, float timeoutS, Action<JObject> onReply, Action onTimeout)
        {
            long id = ++_nextId;
            msg["id"] = id;
            _pending[id] = new Pending { Deadline = Time.realtimeSinceStartup + timeoutS, OnReply = onReply, OnTimeout = onTimeout };
            Send(msg);
            return id;
        }

        /// <summary>Main thread only: deliver replies, fire timeouts, forward unsolicited messages.</summary>
        public void Pump(Action<JObject> onUnsolicited)
        {
            while (_inbox.TryDequeue(out var msg))
            {
                var idTok = msg["id"];
                if (idTok != null && idTok.Type == JTokenType.Integer && _pending.TryGetValue((long)idTok, out var p))
                {
                    _pending.Remove((long)idTok);
                    SafeInvoke(() => p.OnReply(msg));
                }
                else
                {
                    SafeInvoke(() => onUnsolicited(msg));
                }
            }
            if (_pending.Count == 0) return;
            float now = Time.realtimeSinceStartup;
            List<long> expired = null;
            foreach (var kv in _pending)
                if (kv.Value.Deadline <= now) (expired ??= new List<long>()).Add(kv.Key);
            if (expired == null) return;
            foreach (var id in expired)
            {
                var p = _pending[id];
                _pending.Remove(id);
                SafeInvoke(p.OnTimeout);
            }
        }

        private static void SafeInvoke(Action a)
        {
            try { a?.Invoke(); }
            catch (Exception e) { Plugin.Log.LogError($"transport callback failed: {e}"); }
        }

        private void Loop()
        {
            while (_running)
            {
                TcpClient client = null;
                try
                {
                    client = new TcpClient { NoDelay = true };
                    client.Connect(_host, _port);
                    while (_outbox.TryDequeue(out _)) { }   // drop anything queued while disconnected
                    _connected = true;
                    Plugin.Log.LogInfo($"connected to brain at {_host}:{_port}");
                    using (var stream = client.GetStream())
                    using (var reader = new StreamReader(stream, new UTF8Encoding(false)))
                    using (var writer = new StreamWriter(stream, new UTF8Encoding(false)) { AutoFlush = true, NewLine = "\n" })
                    {
                        writer.WriteLine(_helloJson());
                        var readThread = new Thread(() => ReadLoop(reader)) { IsBackground = true, Name = "JevSurvivors.Transport.Read" };
                        readThread.Start();
                        while (_running && client.Connected && readThread.IsAlive)
                        {
                            if (_outbox.TryDequeue(out var line)) writer.WriteLine(line);
                            else Thread.Sleep(2);
                        }
                    }
                }
                catch (Exception e)
                {
                    if (_running) Plugin.Log.LogWarning($"brain link down: {e.Message}");
                }
                finally
                {
                    _connected = false;
                    try { client?.Close(); } catch { }
                }
                if (_running) Thread.Sleep(2000);
            }
        }

        private void ReadLoop(StreamReader reader)
        {
            try
            {
                string line;
                while (_running && (line = reader.ReadLine()) != null)
                {
                    if (line.Length == 0) continue;
                    try { _inbox.Enqueue(JObject.Parse(line)); }
                    catch (Exception e) { Plugin.Log.LogWarning($"bad line from brain: {e.Message}"); }
                }
            }
            catch (Exception)
            {
                // socket closed; Loop reconnects
            }
        }
    }
}
```

- [ ] **Step 2: Wire it into Plugin.cs**

Add `using Newtonsoft.Json.Linq;` at the top. Add the field and the three method bodies:

```csharp
        internal Transport Transport { get; private set; }
```

In `Awake()`, after `Automation = AutoplayOnBoot.Value;` and before the Harmony lines:

```csharp
            Transport = new Transport(Host.Value, Port.Value, HelloJson);
            Transport.Start();
```

Replace `Update()` with:

```csharp
        private void Update()
        {
            if (Input.GetKeyDown(ToggleKey.Value)) SetAutomation(!Automation, "hotkey");
            Transport.Pump(OnUnsolicited);
            Probe.Update();
        }

        private static string HelloJson()
        {
            return new JObject
            {
                ["type"] = "hello",
                ["game_version"] = Application.version,
                ["plugin_version"] = Version,
            }.ToString(Newtonsoft.Json.Formatting.None);
        }

        private void OnUnsolicited(JObject msg)
        {
            var type = (string)msg["type"];
            if (type == "control")
            {
                SetAutomation((bool?)msg["automation"] ?? true, "brain");
                return;
            }
            Log.LogInfo($"ignoring unsolicited message type={type}");
        }
```

And in `OnDestroy()` add `Transport?.Stop();` before the unpatch.

- [ ] **Step 3: Build, deploy, and verify the link**

Terminal 1: `cd brain && uv run jev-vs`. Terminal 2: `scripts/deploy_mod.sh`, then launch the game to the main menu.

Expected in the BepInEx log: `connected to brain at 127.0.0.1:48231`. Expected in the brain log: `plugin connected from ('127.0.0.1', ...)` and the dashboard log line `plugin hello: game 1.16.107 plugin 0.1.0`; the dashboard header's plugin dot turns green. Press PAUSE on the dashboard: BepInEx log shows `automation OFF (brain)`; RESUME shows `automation ON (brain)`. Stop the brain (Ctrl-C): BepInEx log shows `brain link down: ...`; start it again: `connected to brain` appears within a few seconds.

- [ ] **Step 4: Commit**

```bash
git add mod/JevSurvivors/Transport.cs mod/JevSurvivors/Plugin.cs
git commit -m "feat(mod): TCP transport to the brain with request ids, timeouts, and reconnect"
```

---

### Task 4: State sampler and movement override

**Files:**
- Create: `mod/JevSurvivors/StateSampler.cs`
- Create: `mod/JevSurvivors/Movement.cs`
- Modify: `mod/JevSurvivors/Plugin.cs`

**Interfaces:**
- Produces: `StateSampler(Transport t)` with `Update()`, static `bool RunActive()`, static `JObject BuildTick()`, static `JArray Equip(EquipmentManager m)`.
- Produces: static `Movement` with `Vector2 Current`, `string LastChoice`, `Apply(JObject reply)`, `OnTimeout()`, `Expire()`, `Clear()`; Harmony prefix `ProcessRawDirectionPatch` on `CharacterController.ProcessRawDirection`.
- Tick shape is exactly spec section 4 (`player`, `enemies`, `gems`, `pickups`, `screen`).
- Consumes: `Transport.Request`, `GM.Core`, `Stage.GetAllEnemiesInScreenBounds/GetAllGemsInScreenBounds/GetAllPickupsInScreenBounds`, `Stage._mainCamera`, `CameraExtensions.OrthographicBounds`.

- [ ] **Step 1: Write StateSampler.cs**

```csharp
using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using UnityEngine;
using VampireSurvivors.Framework;
using VampireSurvivors.Objects;
using VampireSurvivors.Objects.Items;
using VampireSurvivors.Tools;

namespace JevSurvivors
{
    /// <summary>Sends a raw-state tick at TickHz while a run is active. All numbers are world units relative to the player.</summary>
    public sealed class StateSampler
    {
        private readonly Transport _t;
        private float _next;

        public StateSampler(Transport t) { _t = t; }

        public static bool RunActive()
        {
            var gm = GM.Core;
            return gm != null && gm.Player != null && gm.Stage != null && !gm.IsPaused && !gm.Player.IsDead;
        }

        public void Update()
        {
            if (!Plugin.Automation || !_t.Connected || !RunActive()) return;
            float now = Time.realtimeSinceStartup;
            if (now < _next) return;
            _next = now + 1f / Mathf.Max(0.5f, Plugin.TickHz.Value);
            JObject tick;
            try { tick = BuildTick(); }
            catch (Exception e) { Plugin.Log.LogWarning($"tick build failed: {e.Message}"); return; }
            _t.Request(tick, Plugin.ReplyTimeoutMs.Value / 1000f, Movement.Apply, Movement.OnTimeout);
        }

        public static JObject BuildTick()
        {
            var gm = GM.Core;
            var p = gm.Player;
            var stage = gm.Stage;
            Vector3 pp = p.transform.position;
            Bounds b = stage._mainCamera.OrthographicBounds();
            int cap = Plugin.MaxEntities.Value;

            var enemies = new List<(float d, JObject o)>();
            foreach (var e in stage.GetAllEnemiesInScreenBounds())
            {
                if (e == null || e.IsUnitDead()) continue;
                Vector3 ep = e.transform.position;
                float dx = ep.x - pp.x, dy = ep.y - pp.y;
                enemies.Add((dx * dx + dy * dy, new JObject
                {
                    ["x"] = R(dx), ["y"] = R(dy), ["hp"] = R(e.CurrentHealth()),
                    ["type"] = e.EnemyType.ToString(), ["boss"] = e.IsBoss,
                }));
            }

            var gems = new List<(float d, JObject o)>();
            foreach (var g in stage.GetAllGemsInScreenBounds())
            {
                if (g == null) continue;
                Vector3 gp = g.transform.position;
                float dx = gp.x - pp.x, dy = gp.y - pp.y;
                gems.Add((dx * dx + dy * dy, new JObject { ["x"] = R(dx), ["y"] = R(dy), ["value"] = R(g.Value) }));
            }

            var pickups = new List<(float d, JObject o)>();
            foreach (var pk in stage.GetAllPickupsInScreenBounds())
            {
                if (pk == null || pk is Gem) continue;
                Vector3 kp = pk.transform.position;
                float dx = kp.x - pp.x, dy = kp.y - pp.y;
                pickups.Add((dx * dx + dy * dy, new JObject { ["x"] = R(dx), ["y"] = R(dy), ["kind"] = pk.PickupType.ToString() }));
            }

            return new JObject
            {
                ["type"] = "tick",
                ["t"] = R(gm.SurvivedSeconds),
                ["state"] = new JObject
                {
                    ["player"] = new JObject
                    {
                        ["x"] = R(pp.x), ["y"] = R(pp.y),
                        ["hp"] = R(p.CurrentHealth()), ["max_hp"] = R(p.MaxHp()),
                        ["level"] = p.Level, ["xp"] = R(p.Xp), ["xp_to_next"] = R(gm.LevelUpFactory.XpRequiredToLevelUp),
                        ["minute"] = stage.CurrentMinute, ["seconds"] = R(gm.SurvivedSeconds),
                        ["character"] = p.CharacterType.ToString(),
                        ["weapons"] = Equip(p.WeaponsManager), ["passives"] = Equip(p.AccessoriesManager),
                    },
                    ["enemies"] = Nearest(enemies, cap),
                    ["gems"] = Nearest(gems, cap),
                    ["pickups"] = Nearest(pickups, cap),
                    ["screen"] = new JObject { ["half_w"] = R(b.extents.x), ["half_h"] = R(b.extents.y) },
                },
            };
        }

        public static JArray Equip(EquipmentManager m)
        {
            var a = new JArray();
            if (m == null) return a;
            foreach (var eq in m.ActiveEquipment)
            {
                if (eq == null) continue;
                a.Add(new JObject { ["id"] = eq.Type.ToString(), ["level"] = eq.Level, ["max"] = eq.IsMaxLevel() });
            }
            return a;
        }

        private static JArray Nearest(List<(float d, JObject o)> items, int cap)
        {
            items.Sort((x, y) => x.d.CompareTo(y.d));
            var arr = new JArray();
            for (int i = 0; i < items.Count && i < cap; i++) arr.Add(items[i].o);
            return arr;
        }

        private static float R(float v) => (float)Math.Round(v, 2);
    }
}
```

- [ ] **Step 2: Write Movement.cs**

```csharp
using HarmonyLib;
using Newtonsoft.Json.Linq;
using UnityEngine;
using VampireSurvivors.Framework;
using VsCharacter = VampireSurvivors.Objects.Characters.CharacterController;

namespace JevSurvivors
{
    /// <summary>The latest movement vector from the brain, zeroed after one second of silence.</summary>
    public static class Movement
    {
        public const float StaleAfterS = 1.0f;

        public static Vector2 Current { get; private set; } = Vector2.zero;
        public static string LastChoice { get; private set; } = "stay";
        private static float _appliedAt = -1f;

        public static void Apply(JObject reply)
        {
            if ((string)reply["type"] != "move") return;
            Current = new Vector2((float?)reply["dx"] ?? 0f, (float?)reply["dy"] ?? 0f);
            LastChoice = (string)reply["choice"] ?? "stay";
            _appliedAt = Time.realtimeSinceStartup;
        }

        /// <summary>A late tick keeps the last vector; Expire() zeroes it if silence continues.</summary>
        public static void OnTimeout() { }

        public static void Expire()
        {
            if (_appliedAt >= 0f && Time.realtimeSinceStartup - _appliedAt > StaleAfterS) Clear();
        }

        public static void Clear()
        {
            Current = Vector2.zero;
            LastChoice = "stay";
            _appliedAt = -1f;
        }
    }

    /// <summary>
    /// HandlePlayerInput() writes Rewired axes into _currentDirectionRaw and then calls ProcessRawDirection().
    /// This prefix replaces the raw vector for the main player right before it is processed.
    /// </summary>
    [HarmonyPatch(typeof(VsCharacter), "ProcessRawDirection")]
    internal static class ProcessRawDirectionPatch
    {
        private static void Prefix(VsCharacter __instance)
        {
            if (!Plugin.Automation) return;
            var gm = GM.Core;
            if (gm == null || __instance != gm.Player) return;
            __instance._currentDirectionRaw = Movement.Current;
        }
    }
}
```

- [ ] **Step 3: Wire into Plugin.cs**

Add the property:

```csharp
        internal StateSampler Sampler { get; private set; }
```

In `Awake()` right after `Transport.Start();`:

```csharp
            Sampler = new StateSampler(Transport);
```

Replace `Update()` with:

```csharp
        private void Update()
        {
            if (Input.GetKeyDown(ToggleKey.Value)) SetAutomation(!Automation, "hotkey");
            Transport.Pump(OnUnsolicited);
            Sampler.Update();
            Movement.Expire();
            Probe.Update();
        }
```

In `SetAutomation`, after `Automation = on;` add `if (!on) Movement.Clear();`.

- [ ] **Step 4: Build, deploy, verify with a hand-started run**

Brain running, `scripts/deploy_mod.sh`, launch the game, start any run by hand (menus are still manual in this task).

Expected: the character walks on its own once the run begins. The dashboard direction card updates about four times a second and the radar shows red enemy dots and green gems around the centre. The brain writes `brain/runs/<stamp>/ticks.jsonl` lines (the run log only opens on a `character_select` event, which does not exist yet, so ticks are buffered until Task 5; confirm instead with the dashboard). Press F9: the character stops responding to the brain and your keyboard works; F9 again hands control back. Stop the brain mid-run: within about one second the character stops moving (`Expire`) and the game keeps running.

BepInEx log must show no `tick build failed` lines. If it shows one mentioning `OrthographicBounds`, the extension method lives in `VampireSurvivors.Tools.CameraExtensions`; confirm the `using VampireSurvivors.Tools;` line is present.

- [ ] **Step 5: Commit**

```bash
git add mod/JevSurvivors/StateSampler.cs mod/JevSurvivors/Movement.cs mod/JevSurvivors/Plugin.cs
git commit -m "feat(mod): stream raw state ticks and apply brain movement via ProcessRawDirection prefix"
```

---

### Task 5: Menu driver, part 1: boot to run start

**Files:**
- Create: `mod/JevSurvivors/MenuDriver.cs`
- Create: `mod/JevSurvivors/Patches.cs`
- Delete: `mod/JevSurvivors/Probe.cs`
- Modify: `mod/JevSurvivors/Plugin.cs`

**Interfaces:**
- Produces: `MenuDriver(Plugin plugin, Transport transport)` with static `Instance`, `Update()`, `PageShown(BaseUIPage)`, `PageHidden(BaseUIPage)`, `OnLanding(LandingScreenPage)`, `OnMainMenu(MainMenuPage)`, `OnCharacterSelect(CharacterSelectionPage)`, `OnWeaponSelect(WeaponSelectionPage)`, `OnStageSelect(StageSelectPage)`, `OnRunStarted(MainGamePage)`, counters `RunsStarted`, `RunsFinished`.
- Produces: Harmony patch classes in `Patches.cs`.
- Events sent: `character_select`, `weapon_select`, `stage_select` with option shapes from spec section 4.
- Consumes: `Transport.Request`, `Movement.Clear`, game page methods verified in the decompiled source: `LandingScreenPage.MoveToNextView()`, `MainMenuPage.ShowCharacterSelect()`, `CharacterSelectionPage._characterItemUIs` (Dictionary<CharacterType, CharacterItemUI>), `CharacterItemUI.IsAvailable()`, `CharacterItemUI.CharacterItem.CharacterData`, `CharacterSelectionPage.ShowCharacterInfo(CharacterData, CharacterType, CharacterItemUI)`, `SelectCharacter(bool)`, `ConfirmCharacter()`, `WeaponSelectionPage._spawned` (List<WeaponSelectionItemUI>), `WeaponSelectionItemUI._type/_data`, `WeaponSelectionPage.SelectWeapon(item)/Skip()`, `StageSelectPage._spawned` (List<GameObject> carrying `StageItemUI`), `StageItemUI.Type/GetData()`, `StageSelectPage.SetInfoPanel(StageItemUI, StageData, StageType)`, `SelectStage()`, `ConfirmStage()`.

- [ ] **Step 1: Write MenuDriver.cs**

```csharp
using System;
using System.Collections;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using UnityEngine;
using VampireSurvivors;
using VampireSurvivors.Data;
using VampireSurvivors.Framework;
using VampireSurvivors.UI;

namespace JevSurvivors
{
    /// <summary>
    /// Drives menus using the game's own page methods. Every handler is a coroutine on the Plugin
    /// MonoBehaviour: wait for the page to populate, read options, ask the brain, apply the pick.
    /// A missing or late brain reply always falls back to the first option so the game never stalls.
    /// </summary>
    public sealed class MenuDriver
    {
        public static MenuDriver Instance { get; private set; }

        private readonly Plugin _plugin;
        private readonly Transport _t;
        private readonly Dictionary<BaseUIPage, float> _shownAt = new Dictionary<BaseUIPage, float>();
        private readonly HashSet<BaseUIPage> _nudged = new HashSet<BaseUIPage>();

        /// <summary>Pages with a dedicated handler; the safety net leaves these alone.</summary>
        private static readonly HashSet<Type> Handled = new HashSet<Type>
        {
            typeof(MainMenuPage), typeof(CharacterSelectionPage), typeof(WeaponSelectionPage),
            typeof(StageSelectPage), typeof(MainGamePage),
        };

        public int RunsStarted { get; private set; }
        public int RunsFinished { get; private set; }

        public MenuDriver(Plugin plugin, Transport transport)
        {
            _plugin = plugin;
            _t = transport;
            Instance = this;
        }

        // ------------------------------------------------------------------ tracking
        public void PageShown(BaseUIPage page)
        {
            _shownAt[page] = Time.realtimeSinceStartup;
            Plugin.Log.LogInfo($"page shown: {page.GetType().Name}");
        }

        public void PageHidden(BaseUIPage page)
        {
            _shownAt.Remove(page);
            _nudged.Remove(page);
        }

        public void Update()
        {
            // safety net arrives in Task 6
        }

        // ------------------------------------------------------------------ helpers
        private sealed class ReplyBox
        {
            public JObject Reply;
            public bool Done;
            public bool TimedOut;
        }

        private ReplyBox Ask(JObject evt)
        {
            var box = new ReplyBox();
            if (!_t.Connected)
            {
                box.Done = box.TimedOut = true;
                Plugin.Log.LogWarning($"{evt["event"]}: brain not connected, using default");
                return box;
            }
            _t.Request(evt, Plugin.MenuReplyTimeoutMs.Value / 1000f,
                r => { box.Reply = r; box.Done = true; },
                () => { box.TimedOut = true; box.Done = true; Plugin.Log.LogWarning($"{evt["event"]}: no reply in time, using default"); });
            return box;
        }

        private static int PickIndex(ReplyBox box, int count)
        {
            if (box.Reply != null && (string)box.Reply["type"] == "pick")
            {
                int i = (int?)box.Reply["index"] ?? 0;
                if (i >= 0 && i < count) return i;
            }
            return 0;
        }

        private static JObject Event(string name, JArray options)
        {
            return new JObject { ["type"] = "event", ["event"] = name, ["options"] = options };
        }

        private static bool CanAutomate() => Plugin.Automation;

        private bool RunBudgetLeft() => Plugin.MaxRuns.Value <= 0 || RunsStarted < Plugin.MaxRuns.Value;

        // ------------------------------------------------------------------ boot to run start
        public void OnLanding(LandingScreenPage page) => _plugin.StartCoroutine(Landing(page));

        private IEnumerator Landing(LandingScreenPage page)
        {
            yield return new WaitForSecondsRealtime(Plugin.MenuDelayS.Value);
            if (!CanAutomate() || page == null) yield break;
            Plugin.Log.LogInfo("landing: continuing");
            page.MoveToNextView();
        }

        public void OnMainMenu(MainMenuPage page) => _plugin.StartCoroutine(MainMenu(page));

        private IEnumerator MainMenu(MainMenuPage page)
        {
            float wait = Plugin.MenuDelayS.Value + (RunsFinished > 0 ? Plugin.PauseBetweenRunsS.Value : 0f);
            yield return new WaitForSecondsRealtime(wait);
            if (!CanAutomate() || page == null || !page.gameObject.activeInHierarchy) yield break;
            if (!RunBudgetLeft())
            {
                Plugin.Log.LogInfo($"main menu: MaxRuns={Plugin.MaxRuns.Value} reached, idling");
                yield break;
            }
            Plugin.Log.LogInfo("main menu: opening character select");
            page.ShowCharacterSelect();
        }

        public void OnCharacterSelect(CharacterSelectionPage page) => _plugin.StartCoroutine(CharacterSelect(page));

        private IEnumerator CharacterSelect(CharacterSelectionPage page)
        {
            yield return new WaitForSecondsRealtime(Plugin.MenuDelayS.Value);
            if (!CanAutomate() || page == null) yield break;
            var uis = new List<CharacterItemUI>();
            var options = new JArray();
            foreach (var kv in page._characterItemUIs)
            {
                var ui = kv.Value;
                if (ui == null || !ui.IsAvailable()) continue;
                var data = ui.CharacterItem.CharacterData;
                uis.Add(ui);
                options.Add(new JObject
                {
                    ["id"] = kv.Key.ToString(),
                    ["name"] = $"{data.charName} {data.surname}".Trim(),
                    ["description"] = data.description ?? "",
                    ["starting_weapon"] = data.startingWeapon?.ToString(),
                });
            }
            if (uis.Count == 0)
            {
                Plugin.Log.LogWarning("character select: no available characters");
                yield break;
            }
            var box = Ask(Event("character_select", options));
            while (!box.Done) yield return null;
            var pick = uis[PickIndex(box, uis.Count)];
            Plugin.Log.LogInfo($"character select: {pick.Type} ({(box.TimedOut ? "default" : "brain")})");
            page.ShowCharacterInfo(pick.CharacterItem.CharacterData, pick.Type, pick);
            yield return null;
            page.SelectCharacter(false);
            yield return null;
            page.ConfirmCharacter();
            RunsStarted++;
        }

        public void OnWeaponSelect(WeaponSelectionPage page) => _plugin.StartCoroutine(WeaponSelect(page));

        private IEnumerator WeaponSelect(WeaponSelectionPage page)
        {
            yield return new WaitForSecondsRealtime(Plugin.MenuDelayS.Value);
            if (!CanAutomate() || page == null) yield break;
            var items = new List<WeaponSelectionItemUI>();
            var options = new JArray();
            foreach (var item in page._spawned)
            {
                if (item == null) continue;
                items.Add(item);
                options.Add(new JObject
                {
                    ["index"] = items.Count - 1,
                    ["id"] = item._type.ToString(),
                    ["name"] = item._data?.name ?? item._type.ToString(),
                    ["kind"] = "weapon", ["level"] = 1, ["is_new"] = true,
                    ["description"] = item._data?.description ?? "",
                });
            }
            if (items.Count == 0)
            {
                Plugin.Log.LogInfo("weapon select: nothing offered, skipping");
                page.Skip();
                yield break;
            }
            var box = Ask(Event("weapon_select", options));
            while (!box.Done) yield return null;
            var pick = items[PickIndex(box, items.Count)];
            Plugin.Log.LogInfo($"weapon select: {pick._type}");
            page.SelectWeapon(pick);
        }

        public void OnStageSelect(StageSelectPage page) => _plugin.StartCoroutine(StageSelect(page));

        private IEnumerator StageSelect(StageSelectPage page)
        {
            yield return new WaitForSecondsRealtime(Plugin.MenuDelayS.Value);
            if (!CanAutomate() || page == null) yield break;
            var items = new List<StageItemUI>();
            var options = new JArray();
            foreach (var go in page._spawned)
            {
                var item = go != null ? go.GetComponent<StageItemUI>() : null;
                if (item == null) continue;
                var data = item.GetData();
                if (data == null || !data.unlocked) continue;
                items.Add(item);
                options.Add(new JObject
                {
                    ["id"] = item.Type.ToString(),
                    ["name"] = data.stageName ?? item.Type.ToString(),
                    ["description"] = data.description ?? "",
                });
            }
            if (items.Count == 0)
            {
                Plugin.Log.LogWarning("stage select: no unlocked stages");
                yield break;
            }
            var box = Ask(Event("stage_select", options));
            while (!box.Done) yield return null;
            var pick = items[PickIndex(box, items.Count)];
            Plugin.Log.LogInfo($"stage select: {pick.Type}");
            page.SetInfoPanel(pick, pick.GetData(), pick.Type);
            yield return null;
            page.SelectStage();
            yield return null;
            page.ConfirmStage();
        }

        public void OnRunStarted(MainGamePage page)
        {
            Movement.Clear();
            var gm = GM.Core;
            Plugin.Log.LogInfo($"run started: {gm?.Player?.CharacterType} on {gm?.PlayerOptions?.Config?.SelectedStage}");
        }
    }
}
```

- [ ] **Step 2: Write Patches.cs**

`BaseUIPage.OnShowStart` and `OnHideStart` are patched for tracking only; each page that overrides `OnShowStart` (verified in the decompiled source) gets its own postfix for dispatch. `MainGamePage` does not override it, so it is dispatched from the base postfix.

```csharp
using System;
using HarmonyLib;
using VampireSurvivors;
using VampireSurvivors.UI;

namespace JevSurvivors
{
    internal static class Safe
    {
        public static void Run(string what, Action a)
        {
            try { a(); }
            catch (Exception e) { Plugin.Log.LogError($"{what} failed: {e}"); }
        }
    }

    [HarmonyPatch(typeof(BaseUIPage), "OnShowStart")]
    internal static class BasePageShowPatch
    {
        private static void Postfix(BaseUIPage __instance) => Safe.Run("PageShown", () =>
        {
            MenuDriver.Instance?.PageShown(__instance);
            if (__instance is MainGamePage hud) MenuDriver.Instance?.OnRunStarted(hud);
        });
    }

    [HarmonyPatch(typeof(BaseUIPage), "OnHideStart")]
    internal static class BasePageHidePatch
    {
        private static void Postfix(BaseUIPage __instance) => Safe.Run("PageHidden", () => MenuDriver.Instance?.PageHidden(__instance));
    }

    [HarmonyPatch(typeof(LandingScreenPage), "Start")]
    internal static class LandingPatch
    {
        private static void Postfix(LandingScreenPage __instance) => Safe.Run("OnLanding", () => MenuDriver.Instance?.OnLanding(__instance));
    }

    [HarmonyPatch(typeof(MainMenuPage), "OnShowStart")]
    internal static class MainMenuPatch
    {
        private static void Postfix(MainMenuPage __instance) => Safe.Run("OnMainMenu", () => MenuDriver.Instance?.OnMainMenu(__instance));
    }

    [HarmonyPatch(typeof(CharacterSelectionPage), "OnShowStart")]
    internal static class CharacterSelectPatch
    {
        private static void Postfix(CharacterSelectionPage __instance) => Safe.Run("OnCharacterSelect", () => MenuDriver.Instance?.OnCharacterSelect(__instance));
    }

    [HarmonyPatch(typeof(WeaponSelectionPage), "OnShowStart")]
    internal static class WeaponSelectPatch
    {
        private static void Postfix(WeaponSelectionPage __instance) => Safe.Run("OnWeaponSelect", () => MenuDriver.Instance?.OnWeaponSelect(__instance));
    }

    [HarmonyPatch(typeof(StageSelectPage), "OnShowStart")]
    internal static class StageSelectPatch
    {
        private static void Postfix(StageSelectPage __instance) => Safe.Run("OnStageSelect", () => MenuDriver.Instance?.OnStageSelect(__instance));
    }
}
```

- [ ] **Step 3: Update Plugin.cs and delete Probe.cs**

Delete `mod/JevSurvivors/Probe.cs`. In `Plugin.cs` add:

```csharp
        internal MenuDriver Menu { get; private set; }
```

In `Awake()` after `Sampler = new StateSampler(Transport);`:

```csharp
            Menu = new MenuDriver(this, Transport);
```

Replace `Update()` with:

```csharp
        private void Update()
        {
            if (Input.GetKeyDown(ToggleKey.Value)) SetAutomation(!Automation, "hotkey");
            Transport.Pump(OnUnsolicited);
            Sampler.Update();
            Menu.Update();
            Movement.Expire();
        }
```

- [ ] **Step 4: Build, deploy, verify a hands-off start**

Brain running, `scripts/deploy_mod.sh`, launch the game, touch nothing.

Expected BepInEx log sequence (character and stage names will differ):
```
landing: continuing
page shown: MainMenuPage
main menu: opening character select
page shown: CharacterSelectionPage
character select: ANTONIO (brain)
page shown: StageSelectPage
stage select: FOREST
page shown: MainGamePage
run started: ANTONIO on FOREST
```
Expected on the dashboard: the character and stage cards fill with bars, the log shows both picks, the run counter shows a run started, and once the run begins the direction card and radar animate. `brain/runs/<stamp>/events.jsonl` has two lines.

If `page shown: MainGamePage` never appears, the HUD page does not call `base.OnShowStart`; add a dedicated patch on `MainGamePage` `OnShowFinish` that calls `OnRunStarted` and remove the `is MainGamePage` line from `BasePageShowPatch`. If a `WeaponSelectionPage` appears for the chosen character, the log must show `weapon select: ...` between the character and stage lines.

If the character page shows the wrong character confirmed (the previously selected one), insert an extra `yield return null;` between `ShowCharacterInfo` and `SelectCharacter`; the page updates the multiplayer slot on the frame after `ShowCharacterInfo`.

- [ ] **Step 5: Commit**

```bash
git add -A mod/JevSurvivors
git commit -m "feat(mod): menu driver takes the game from boot to a Jev-chosen run start"
```

---

### Task 6: Menu driver, part 2: in-run pages, game over, run loop, safety net

**Files:**
- Modify: `mod/JevSurvivors/MenuDriver.cs`
- Modify: `mod/JevSurvivors/Patches.cs`

**Interfaces:**
- Produces on `MenuDriver`: `OnLevelUp(LevelUpPage)`, `OnArcana(ArcanaMainSelectionPage)`, `OnTreasure(OpenTreasurePage)`, `OnItemFound(ItemFoundPage)`, `OnCharacterFound(CharacterFoundPage)`, `OnGameOver(GameOverPage)`, `OnRecap(RecapPage)`, a working `Update()` safety net.
- Events sent: `level_up` (with `build`), `arcana_select`, `game_over` (with `summary`).
- Consumes (verified in decompiled source): `LevelUpPage.LevelUpItems` (List<LevelUpItemUI>), `LevelUpPage.EnableLevelupOptions()` as the ready hook, `LevelUpPage.Skip()`, `LevelUpItemUI._type/_itemType/_data/_levelData/_itemData/_currentLevel/_isLimitBreak`, `IsWeapon()/IsPowerUp()/IsNew()/Select()`, `WeaponData.evoSynergy` (WeaponType[]), `ArcanaMainSelectionPage._hasFinishedPopulationAnimation/_spawned`, `ArcanaCardUI.GetData()/GetArcanaType()`, `ArcanaMainSelectionPage.SetInfo(ArcanaData, ArcanaType, ArcanaCardUI)/Select()/Skip()`, `OpenTreasurePage._canSkip/_animCanBeSkippedPastThisPoint/_isSkipped/_doneButtonPressed/DoneButtonLeftArrow/Skip()/ClaimTreasure()`, `ItemFoundPage.Receive()`, `CharacterFoundPage.Reveal()/CollectCharacter()`, `GameOverPage._stageComplete/Quit()`, `RecapPage.DoneClicked()`, `MainGamePage.KillsText`, `GameManager.SurvivedSeconds`, `BaseUIPage.OnEnterPressed()`.

- [ ] **Step 1: Extend the `Handled` set and add the in-run handlers to MenuDriver.cs**

Replace the `Handled` initializer with:

```csharp
        private static readonly HashSet<Type> Handled = new HashSet<Type>
        {
            typeof(MainMenuPage), typeof(CharacterSelectionPage), typeof(WeaponSelectionPage), typeof(StageSelectPage),
            typeof(MainGamePage), typeof(LevelUpPage), typeof(ArcanaMainSelectionPage), typeof(OpenTreasurePage),
            typeof(ItemFoundPage), typeof(CharacterFoundPage), typeof(GameOverPage), typeof(RecapPage),
        };
```

Add these methods inside the class (after `OnRunStarted`):

```csharp
        // ------------------------------------------------------------------ in-run pages
        public void OnLevelUp(LevelUpPage page) => _plugin.StartCoroutine(LevelUp(page));

        private IEnumerator LevelUp(LevelUpPage page)
        {
            yield return null;   // let EnableLevelupOptions finish
            if (!CanAutomate() || page == null) yield break;
            var items = new List<LevelUpItemUI>();
            var options = new JArray();
            var owned = OwnedTypes();
            foreach (var ui in page.LevelUpItems)
            {
                if (ui == null) continue;
                items.Add(ui);
                bool isWeapon = ui._type != WeaponType.VOID;
                string id = isWeapon ? ui._type.ToString() : ui._itemType.ToString();
                string kind = ui._isLimitBreak ? "limit_break" : ui.IsWeapon() ? "weapon" : ui.IsPowerUp() ? "passive" : "item";
                string name = ui._data?.name ?? ui._itemData?.name ?? id;
                string desc = ui._levelData?.description ?? ui._data?.description ?? ui._itemData?.description ?? "";
                options.Add(new JObject
                {
                    ["index"] = items.Count - 1, ["id"] = id, ["name"] = name, ["kind"] = kind,
                    ["level"] = ui._currentLevel, ["is_new"] = ui.IsNew(), ["description"] = desc,
                    ["evolution_ready"] = EvolutionReady(ui, owned),
                });
            }
            if (items.Count == 0)
            {
                Plugin.Log.LogWarning("level up: no items offered, skipping");
                page.Skip();
                yield break;
            }
            var evt = Event("level_up", options);
            evt["build"] = Build();
            var box = Ask(evt);
            while (!box.Done) yield return null;
            int idx = PickIndex(box, items.Count);
            Plugin.Log.LogInfo($"level up: picked {(string)options[idx]["name"]} ({(box.TimedOut ? "default" : "brain")})");
            items[idx].Select();
        }

        private static HashSet<WeaponType> OwnedTypes()
        {
            var set = new HashSet<WeaponType>();
            var p = GM.Core?.Player;
            if (p == null) return set;
            foreach (var e in p.WeaponsManager.ActiveEquipment) if (e != null) set.Add(e.Type);
            foreach (var e in p.AccessoriesManager.ActiveEquipment) if (e != null) set.Add(e.Type);
            return set;
        }

        /// <summary>True when this weapon option's evolution partners are all owned (spec section 4).</summary>
        private static bool EvolutionReady(LevelUpItemUI ui, HashSet<WeaponType> owned)
        {
            if (!ui.IsWeapon() || ui._data == null || ui._data.evoSynergy == null || ui._data.evoSynergy.Length == 0) return false;
            foreach (var t in ui._data.evoSynergy) if (!owned.Contains(t)) return false;
            return true;
        }

        private static JObject Build()
        {
            var gm = GM.Core;
            var p = gm?.Player;
            var weapons = new JArray();
            var passives = new JArray();
            var b = new JObject { ["weapons"] = weapons, ["passives"] = passives };
            if (p == null) return b;
            foreach (var e in p.WeaponsManager.ActiveEquipment) if (e != null) weapons.Add($"{e.Type} L{e.Level}");
            foreach (var e in p.AccessoriesManager.ActiveEquipment) if (e != null) passives.Add($"{e.Type} L{e.Level}");
            b["level"] = p.Level;
            b["minute"] = gm.Stage != null ? gm.Stage.CurrentMinute : 0;
            return b;
        }

        public void OnArcana(ArcanaMainSelectionPage page) => _plugin.StartCoroutine(Arcana(page));

        private IEnumerator Arcana(ArcanaMainSelectionPage page)
        {
            float deadline = Time.realtimeSinceStartup + 6f;
            while (page != null && !page._hasFinishedPopulationAnimation && Time.realtimeSinceStartup < deadline) yield return null;
            yield return new WaitForSecondsRealtime(0.5f);
            if (!CanAutomate() || page == null) yield break;
            var cards = new List<ArcanaCardUI>();
            var options = new JArray();
            foreach (var go in page._spawned)
            {
                var card = go != null ? go.GetComponent<ArcanaCardUI>() : null;
                var data = card != null ? card.GetData() : null;
                if (data == null || !data.unlocked) continue;
                cards.Add(card);
                options.Add(new JObject
                {
                    ["index"] = cards.Count - 1, ["id"] = card.GetArcanaType().ToString(), ["name"] = data.name ?? "",
                    ["kind"] = "arcana", ["level"] = 1, ["is_new"] = true, ["description"] = data.description ?? "",
                });
            }
            if (cards.Count == 0)
            {
                Plugin.Log.LogInfo("arcana: nothing selectable, skipping");
                page.Skip();
                yield break;
            }
            var box = Ask(Event("arcana_select", options));
            while (!box.Done) yield return null;
            var pick = cards[PickIndex(box, cards.Count)];
            Plugin.Log.LogInfo($"arcana: {pick.GetArcanaType()}");
            page.SetInfo(pick.GetData(), pick.GetArcanaType(), pick);
            yield return null;
            page.Select();
        }

        public void OnTreasure(OpenTreasurePage page) => _plugin.StartCoroutine(Treasure(page));

        private IEnumerator Treasure(OpenTreasurePage page)
        {
            float deadline = Time.realtimeSinceStartup + 25f;
            while (page != null && page.gameObject.activeInHierarchy && Time.realtimeSinceStartup < deadline)
            {
                if (!CanAutomate()) yield break;
                if (page._canSkip && page._animCanBeSkippedPastThisPoint && !page._isSkipped) page.Skip();
                if (page.DoneButtonLeftArrow != null && page.DoneButtonLeftArrow.activeInHierarchy && !page._doneButtonPressed)
                {
                    Plugin.Log.LogInfo("treasure: claiming");
                    page.ClaimTreasure();
                    yield break;
                }
                yield return new WaitForSecondsRealtime(0.25f);
            }
        }

        public void OnItemFound(ItemFoundPage page) => _plugin.StartCoroutine(Dismiss(page, () => page.Receive(), "item found"));

        public void OnCharacterFound(CharacterFoundPage page) => _plugin.StartCoroutine(CharacterFound(page));

        private IEnumerator CharacterFound(CharacterFoundPage page)
        {
            yield return new WaitForSecondsRealtime(Plugin.MenuDelayS.Value);
            if (!CanAutomate() || page == null) yield break;
            page.Reveal();
            yield return new WaitForSecondsRealtime(1.5f);
            if (page != null) page.CollectCharacter();
        }

        private IEnumerator Dismiss(BaseUIPage page, Action action, string label)
        {
            yield return new WaitForSecondsRealtime(Plugin.MenuDelayS.Value);
            if (!CanAutomate() || page == null) yield break;
            Plugin.Log.LogInfo($"{label}: dismissing");
            action();
        }

        public void OnGameOver(GameOverPage page) => _plugin.StartCoroutine(GameOver(page));

        private IEnumerator GameOver(GameOverPage page)
        {
            Movement.Clear();
            var gm = GM.Core;
            var p = gm?.Player;
            var summary = new JObject
            {
                ["character"] = p?.CharacterType.ToString(),
                ["stage"] = gm?.PlayerOptions?.Config?.SelectedStage.ToString(),
                ["seconds"] = gm != null ? Mathf.RoundToInt(gm.SurvivedSeconds) : 0,
                ["level"] = p?.Level ?? 0,
                ["kills"] = ReadKills(),
                ["stage_complete"] = page._stageComplete,
            };
            RunsFinished++;
            Plugin.Log.LogInfo($"game over: {summary.ToString(Newtonsoft.Json.Formatting.None)}");
            if (_t.Connected)
                _t.Request(new JObject { ["type"] = "event", ["event"] = "game_over", ["summary"] = summary }, 2f, _ => { }, () => { });
            yield return new WaitForSecondsRealtime(2f);
            if (!CanAutomate() || page == null) yield break;
            page.Quit();
        }

        private static int ReadKills()
        {
            var hud = UnityEngine.Object.FindFirstObjectByType<MainGamePage>();
            string text = hud != null && hud.KillsText != null ? hud.KillsText.text : null;
            if (string.IsNullOrEmpty(text)) return 0;
            var digits = new System.Text.StringBuilder();
            foreach (char c in text) if (char.IsDigit(c)) digits.Append(c);
            return int.TryParse(digits.ToString(), out var n) ? n : 0;
        }

        public void OnRecap(RecapPage page) => _plugin.StartCoroutine(Dismiss(page, () => page.DoneClicked(), "recap"));
```

Replace the empty `Update()` with the safety net:

```csharp
        /// <summary>Any tracked page without a handler that stays open too long gets its Enter action once.</summary>
        public void Update()
        {
            if (!CanAutomate() || _shownAt.Count == 0) return;
            float now = Time.realtimeSinceStartup;
            foreach (var kv in _shownAt)
            {
                var page = kv.Key;
                if (page == null || Handled.Contains(page.GetType()) || _nudged.Contains(page)) continue;
                if (now - kv.Value < Plugin.UnknownPageTimeoutS.Value || !page.gameObject.activeInHierarchy) continue;
                _nudged.Add(page);
                Plugin.Log.LogWarning($"unknown page {page.GetType().Name} open for {now - kv.Value:F0}s; pressing Enter for it");
                try { page.OnEnterPressed(); }
                catch (Exception e) { Plugin.Log.LogError($"OnEnterPressed on {page.GetType().Name} failed: {e.Message}"); }
                break;
            }
        }
```

- [ ] **Step 2: Add the patches to Patches.cs**

`OpenTreasurePage` does not override `OnShowStart`, so it is dispatched from the base postfix; extend `BasePageShowPatch`'s lambda:

```csharp
            MenuDriver.Instance?.PageShown(__instance);
            if (__instance is MainGamePage hud) MenuDriver.Instance?.OnRunStarted(hud);
            if (__instance is OpenTreasurePage treasure) MenuDriver.Instance?.OnTreasure(treasure);
```

Append these classes:

```csharp
    [HarmonyPatch(typeof(LevelUpPage), "EnableLevelupOptions")]
    internal static class LevelUpPatch
    {
        private static void Postfix(LevelUpPage __instance) => Safe.Run("OnLevelUp", () => MenuDriver.Instance?.OnLevelUp(__instance));
    }

    [HarmonyPatch(typeof(ArcanaMainSelectionPage), "OnShowStart")]
    internal static class ArcanaPatch
    {
        private static void Postfix(ArcanaMainSelectionPage __instance) => Safe.Run("OnArcana", () => MenuDriver.Instance?.OnArcana(__instance));
    }

    [HarmonyPatch(typeof(ItemFoundPage), "OnShowStart")]
    internal static class ItemFoundPatch
    {
        private static void Postfix(ItemFoundPage __instance) => Safe.Run("OnItemFound", () => MenuDriver.Instance?.OnItemFound(__instance));
    }

    [HarmonyPatch(typeof(CharacterFoundPage), "OnShowStart")]
    internal static class CharacterFoundPatch
    {
        private static void Postfix(CharacterFoundPage __instance) => Safe.Run("OnCharacterFound", () => MenuDriver.Instance?.OnCharacterFound(__instance));
    }

    [HarmonyPatch(typeof(GameOverPage), "OnShowStart")]
    internal static class GameOverPatch
    {
        private static void Postfix(GameOverPage __instance) => Safe.Run("OnGameOver", () => MenuDriver.Instance?.OnGameOver(__instance));
    }

    [HarmonyPatch(typeof(RecapPage), "OnShowStart")]
    internal static class RecapPatch
    {
        private static void Postfix(RecapPage __instance) => Safe.Run("OnRecap", () => MenuDriver.Instance?.OnRecap(__instance));
    }
```

- [ ] **Step 3: Build, deploy, verify a full loop with MaxRuns=2**

Edit `<game>/BepInEx/config/JevSurvivors.cfg`: set `MaxRuns = 2` (created on first run of Task 2). Brain running, `scripts/deploy_mod.sh`, launch, touch nothing, watch until the second run ends.

Expected BepInEx log (in order, repeated twice for the two runs, plus level-ups):
```
run started: ...
page shown: LevelUpPage
level up: picked Whip (brain)
page shown: OpenTreasurePage        (only if a chest was opened)
treasure: claiming
page shown: GameOverPage
game over: {"character":"ANTONIO","stage":"FOREST","seconds":312,"level":11,"kills":540,"stage_complete":false}
page shown: RecapPage
recap: dismissing
page shown: MainMenuPage
main menu: opening character select
...
main menu: MaxRuns=2 reached, idling
```
Expected on the dashboard: the level-up card fills at every level-up with the chosen item highlighted, the runs table gains a row after each game over, and the run log directory has `summary.json` with `character`, `stage`, `seconds`, `level`, `kills`, `ticks` greater than 0 and `events` greater than 2.

If a page is logged as `unknown page X open for 10s; pressing Enter for it` during the loop, that page needs a handler: add a `case` for it following the `Dismiss` pattern and a patch, and add its type to `Handled`.

If the level-up pick is applied but the page does not close, the item `Select()` was called before the buttons were enabled: change the first line of `LevelUp` to `yield return new WaitForSecondsRealtime(0.3f);`.

Reset `MaxRuns = 0` afterwards.

- [ ] **Step 4: Commit**

```bash
git add mod/JevSurvivors/MenuDriver.cs mod/JevSurvivors/Patches.cs
git commit -m "feat(mod): handle level-ups, arcana, treasure, unlock popups, game over, and loop runs"
```

---

### Task 7: README and the hands-off acceptance run

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: everything above plus the brain plan's `uv run jev-vs` and the dashboard at `http://127.0.0.1:48232/`.

- [ ] **Step 1: Write README.md**

```markdown
# Jev plays Vampire Survivors

TypeSafe's Jev model picks the character, the stage, every level-up, and the walking
direction four times a second, in the real Steam game, with a live ops dashboard.

Design: `docs/superpowers/specs/2026-09-17-jev-vampire-survivors-design.md`.

## One-time setup

1. `curl -sSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 8.0` (installs to `~/.dotnet`)
2. `scripts/install_bepinex.sh`, then set the Steam launch option for Vampire Survivors to `./run_bepinex.sh %command%`
3. `scripts/deploy_mod.sh` (builds the plugin into `<game>/BepInEx/plugins/JevSurvivors/`)
4. `export TYPESAFE_API_KEY=...` in the shell that runs the brain

## Play

```bash
cd brain && uv run jev-vs        # brain + dashboard at http://127.0.0.1:48232/
```

Then launch Vampire Survivors from Steam and touch nothing. F9 in the game, or PAUSE on the
dashboard, hands control back to you; press again to resume.

Run logs land in `brain/runs/<timestamp>/` (`ticks.jsonl`, `events.jsonl`, `summary.json`).

## Tuning

- Questions and thresholds: `brain/jev_vs/questions.py` (the only file Jev's wording lives in).
- Brain ports, tick rate, model, timeouts: `brain/config.toml`.
- Plugin timing, entity caps, run count, hotkey: `<game>/BepInEx/config/JevSurvivors.cfg`.

## Develop

- Brain tests: `cd brain && uv run pytest` (`uv run pytest -m live` calls the real API).
- Replay a run into the brain without the game: `uv run --project brain python scripts/fake_plugin.py --replay brain/runs/<stamp>`.
- Read game internals: `scripts/decompile.sh` writes C# to `decompiled/`.
- Plugin log: `<game>/BepInEx/LogOutput.log`.
```

- [ ] **Step 2: Acceptance run**

With `MaxRuns = 0`, brain running with a real API key, launch the game and leave it for one full run.

Checklist (all must hold):
- No key or mouse input after launch until the second run's character select appears.
- Dashboard: plugin and jev dots green; direction card updating; level-up, character, and stage cards populated; radar moving; runs table gains a row; `jev` count far exceeds `fallback` count in the header.
- `brain/runs/<stamp>/summary.json` exists with `ticks` in the thousands for a multi-minute run and `fallback_calls` a small fraction of `jev_calls`.
- BepInEx log contains no `failed:` lines from the plugin and no `unknown page` warnings.
- F9 during a run stops the automation and the character responds to the keyboard; F9 again resumes; the dashboard PAUSE button does the same.

Paste the tail of `summary.json` and the dashboard header numbers into the commit message.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: setup and play instructions; acceptance run recorded"
```

---

## Self-review notes

- Spec coverage: section 6 responsibilities map to Transport (Task 3), tick sampler and movement (Task 4), menu driver and safety net (Tasks 5, 6), kill switch and control (Tasks 2, 3), config (Task 2). Section 7 run loop is Tasks 5 and 6. Section 8 failure table: brain down and late replies are handled in Transport plus `Movement.Expire` and `PickIndex` defaults; patch exceptions are caught in `Safe.Run`; unknown pages by the safety net; F9 by `SetAutomation`.
- Spec section 10's spike (BepInEx viability, target framework, publicizer) is Tasks 1 and 2.
- Type names used across tasks match: `Transport.Request` signature in Task 3 is what `StateSampler` (Task 4) and `MenuDriver.Ask` (Task 5) call; `Movement.Apply/OnTimeout/Expire/Clear` defined in Task 4 are used in Tasks 4, 5, 6; `StateSampler.Equip` is public for reuse.
