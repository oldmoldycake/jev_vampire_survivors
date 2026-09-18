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
