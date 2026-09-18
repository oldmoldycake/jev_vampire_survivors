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
            if (__instance is OpenTreasurePage treasure) MenuDriver.Instance?.OnTreasure(treasure);
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

    [HarmonyPatch(typeof(WarningPage), "OnShowStart")]
    internal static class WarningPatch
    {
        private static void Postfix(WarningPage __instance) => Safe.Run("OnWarning", () => MenuDriver.Instance?.OnWarning(__instance));
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

    [HarmonyPatch(typeof(PausePage), "OnShowStart")]
    internal static class PausePatch
    {
        private static void Postfix(PausePage __instance) => Safe.Run("OnPause", () => MenuDriver.Instance?.OnPause(__instance));
    }
}
