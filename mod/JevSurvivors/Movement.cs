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
