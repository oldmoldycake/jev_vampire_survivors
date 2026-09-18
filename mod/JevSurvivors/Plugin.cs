using BepInEx;
using BepInEx.Configuration;
using BepInEx.Logging;
using HarmonyLib;
using Newtonsoft.Json.Linq;
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

        internal Transport Transport { get; private set; }

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
            Transport = new Transport(Host.Value, Port.Value, HelloJson);
            Transport.Start();
            _harmony = new Harmony(Id);
            _harmony.PatchAll(typeof(Plugin).Assembly);
            Log.LogInfo($"{Name} {Version} loaded; automation={Automation}");
        }

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

        public void SetAutomation(bool on, string why)
        {
            Automation = on;
            Log.LogInfo($"automation {(on ? "ON" : "OFF")} ({why})");
        }

        private void OnDestroy()
        {
            Transport?.Stop();
            _harmony?.UnpatchSelf();
        }
    }
}
