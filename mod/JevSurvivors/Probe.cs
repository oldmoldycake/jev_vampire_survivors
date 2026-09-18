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
            Plugin.Log.LogInfo($"probe: main menu shown; start button present={__instance._StartButton != null}");
        }
    }

    [HarmonyPatch(typeof(LandingScreenPage), "Start")]
    internal static class ProbeLandingPatch
    {
        private static void Postfix(LandingScreenPage __instance)
        {
            Plugin.Log.LogInfo($"probe: landing screen shown; signal bus present={__instance._signalBus != null}");
        }
    }
}
