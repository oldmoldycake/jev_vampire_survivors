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
            typeof(WarningPage), typeof(MainMenuPage), typeof(CharacterSelectionPage), typeof(WeaponSelectionPage),
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
        public void OnWarning(WarningPage page) => _plugin.StartCoroutine(Warning(page));

        private IEnumerator Warning(WarningPage page)
        {
            float deadline = Time.realtimeSinceStartup + 10f;
            while (page != null && page._isWaiting && page._currentTime <= page.WaitDuration && Time.realtimeSinceStartup < deadline)
                yield return null;
            yield return new WaitForSecondsRealtime(Plugin.MenuDelayS.Value);
            if (!CanAutomate() || page == null || !page._isWaiting) yield break;
            Plugin.Log.LogInfo("warning page: continuing");
            page.Complete();
        }

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
