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
            typeof(WarningPage), typeof(MainMenuPage), typeof(CharacterSelectionPage), typeof(WeaponSelectionPage), typeof(StageSelectPage),
            typeof(MainGamePage), typeof(LevelUpPage), typeof(ArcanaMainSelectionPage), typeof(OpenTreasurePage),
            typeof(ItemFoundPage), typeof(CharacterFoundPage), typeof(GameOverPage), typeof(RecapPage), typeof(PausePage),
        };

        /// <summary>Decorative pages the safety net must never nudge.</summary>
        private static readonly HashSet<Type> Ignored = new HashSet<Type>
        {
            typeof(BackgroundPage), typeof(MenuBannerPage),
        };

        public int RunsStarted { get; private set; }
        /// <summary>True between a run starting and that run actually ending. A revive re-shows
        /// MainGamePage, so without this a revived run would be counted against MaxRuns twice.</summary>
        private bool _runInProgress;
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
            _nudged.Remove(page);
            PruneDeadPages();
            _shownAt[page] = Time.realtimeSinceStartup;
            Plugin.Log.LogInfo($"page shown: {page.GetType().Name}");
        }

        /// <summary>Drops _shownAt entries for pages Unity has already destroyed, so the dictionary can't grow with stale references.</summary>
        private void PruneDeadPages()
        {
            List<BaseUIPage> dead = null;
            foreach (var key in _shownAt.Keys)
                if (key == null) (dead ??= new List<BaseUIPage>()).Add(key);
            if (dead == null) return;
            foreach (var key in dead) _shownAt.Remove(key);
        }

        public void PageHidden(BaseUIPage page)
        {
            _shownAt.Remove(page);
            _nudged.Remove(page);
        }

        /// <summary>Any tracked page without a handler that stays open too long gets its Enter action once.</summary>
        public void Update()
        {
            if (!CanAutomate() || _shownAt.Count == 0) return;
            float now = Time.realtimeSinceStartup;
            foreach (var kv in _shownAt)
            {
                var page = kv.Key;
                if (page == null || Handled.Contains(page.GetType()) || Ignored.Contains(page.GetType()) || _nudged.Contains(page)) continue;
                if (now - kv.Value < Plugin.UnknownPageTimeoutS.Value || !page.gameObject.activeInHierarchy) continue;
                _nudged.Add(page);
                Plugin.Log.LogWarning($"unknown page {page.GetType().Name} open for {now - kv.Value:F0}s; pressing Enter for it");
                try { page.OnEnterPressed(); }
                catch (Exception e) { Plugin.Log.LogError($"OnEnterPressed on {page.GetType().Name} failed: {e.Message}"); }
                break;
            }
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
            if (!CanAutomate() || page == null || !page.gameObject.activeInHierarchy) yield break;
            var pick = uis[PickIndex(box, uis.Count)];
            Plugin.Log.LogInfo($"character select: {pick.Type} ({(box.TimedOut ? "default" : "brain")})");
            page.ShowCharacterInfo(pick.CharacterItem.CharacterData, pick.Type, pick);
            yield return null;
            page.SelectCharacter(false);
            yield return null;
            page.ConfirmCharacter();
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
            if (!CanAutomate() || page == null || !page.gameObject.activeInHierarchy) yield break;
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
            if (!CanAutomate() || page == null || !page.gameObject.activeInHierarchy) yield break;
            var pick = items[PickIndex(box, items.Count)];
            Plugin.Log.LogInfo($"stage select: {pick.Type}");
            page.SetInfoPanel(pick, pick.GetData(), pick.Type);
            yield return null;
            page.SelectStage();
            yield return null;
            page._HyperModeTickBox?.InitialSet(false);
            page._HurryModeTickBox?.InitialSet(false);
            page._MazzoModeTickBox?.InitialSet(false);
            page._LimitBreakTickBox?.InitialSet(false);
            page._InverseModeTickBox?.InitialSet(false);
            page._EndlessModeTickBox?.InitialSet(false);
            // ConfirmStage() only re-derives Config.SelectedHyper/Hurry/Mazzo from the tick boxes' IsOn
            // state; SelectedLimitBreak/SelectedInverse/SelectedReapers are otherwise only written by the
            // tick box's OnToggle callback, which InitialSet() does not fire (verified against decompiled
            // TickBoxUI.InitialSet and StageSelectPage.ConfirmStage), so zero those Config fields directly too.
            var cfg = page._playerOptions?.Config;
            if (cfg != null)
            {
                cfg.SelectedLimitBreak = false;
                cfg.SelectedInverse = false;
                cfg.SelectedReapers = false;
            }
            Plugin.Log.LogInfo("stage select: modifiers forced off");
            page.ConfirmStage();
        }

        public void OnRunStarted(MainGamePage page)
        {
            Movement.Clear();
            StateSampler.ResetTracking();
            if (!_runInProgress)
            {
                _runInProgress = true;
                RunsStarted++;   // an actual run start, not a character confirm that never reached gameplay, and not a revive
            }
            var gm = GM.Core;
            Plugin.Log.LogInfo($"run started: {gm?.Player?.CharacterType} on {gm?.PlayerOptions?.Config?.SelectedStage}");
        }

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
                // LevelUpItemUI._currentLevel is never assigned by the game (verified in decompiled
                // LevelUpItemUI.cs), so read the level from the WeaponData the option actually carries.
                int level = ui._isLimitBreak ? ui._data?.level ?? 1
                    : ui._type == WeaponType.VOID ? 1
                    : ui._levelData?.level ?? ui._data?.level ?? 1;
                options.Add(new JObject
                {
                    ["index"] = items.Count - 1, ["id"] = id, ["name"] = name, ["kind"] = kind,
                    ["level"] = level, ["is_new"] = ui.IsNew(), ["description"] = desc,
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
            if (!CanAutomate() || page == null || !page.gameObject.activeInHierarchy) yield break;
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
            if (page._unlockedCards != null && page._unlockedCards.Count > 0)
            {
                foreach (var card in page._unlockedCards)
                {
                    if (card == null) continue;
                    var data = card.GetData();
                    if (data == null) continue;
                    AddArcanaOption(card, data, cards, options);
                }
            }
            else
            {
                foreach (var go in page._spawned)
                {
                    var card = go != null ? go.GetComponent<ArcanaCardUI>() : null;
                    var data = card != null ? card.GetData() : null;
                    if (data == null || !data.unlocked) continue;
                    AddArcanaOption(card, data, cards, options);
                }
            }
            if (cards.Count == 0)
            {
                Plugin.Log.LogInfo("arcana: nothing selectable, skipping");
                page.Skip();
                yield break;
            }
            var box = Ask(Event("arcana_select", options));
            while (!box.Done) yield return null;
            if (!CanAutomate() || page == null || !page.gameObject.activeInHierarchy) yield break;
            var pick = cards[PickIndex(box, cards.Count)];
            Plugin.Log.LogInfo($"arcana: {pick.GetArcanaType()}");
            page.SetInfo(pick.GetData(), pick.GetArcanaType(), pick);
            yield return null;
            page.Select();
            yield return new WaitForSecondsRealtime(3f);
            if (page != null && page.gameObject.activeInHierarchy)
            {
                Plugin.Log.LogWarning("arcana: select did not close the page, skipping");
                page.Skip();
            }
        }

        private static void AddArcanaOption(ArcanaCardUI card, ArcanaData data, List<ArcanaCardUI> cards, JArray options)
        {
            cards.Add(card);
            options.Add(new JObject
            {
                ["index"] = cards.Count - 1, ["id"] = card.GetArcanaType().ToString(), ["name"] = data.name ?? "",
                ["kind"] = "arcana", ["level"] = 1, ["is_new"] = true, ["description"] = data.description ?? "",
            });
        }

        public void OnTreasure(OpenTreasurePage page) => _plugin.StartCoroutine(Treasure(page));

        private IEnumerator Treasure(OpenTreasurePage page)
        {
            float deadline = Time.realtimeSinceStartup + 120f;
            yield return new WaitForSecondsRealtime(0.5f);
            while (page != null && page.gameObject.activeInHierarchy && Time.realtimeSinceStartup < deadline)
            {
                if (!CanAutomate()) yield break;
                if (!page._openButtonPressed)
                {
                    Plugin.Log.LogInfo("treasure: opening");
                    page.OpenTreasure();
                }
                else if (page._isPlaying && page._canSkip && page._animCanBeSkippedPastThisPoint && !page._isSkipped)
                {
                    page.Skip();
                }
                if (page.DoneButton != null && page.DoneButton.activeInHierarchy && !page._doneButtonPressed)
                {
                    Plugin.Log.LogInfo("treasure: claiming");
                    page.ClaimTreasure();
                    yield break;
                }
                yield return new WaitForSecondsRealtime(0.25f);
            }
            if (page != null && page.gameObject.activeInHierarchy) Plugin.Log.LogWarning("treasure: still open after 120s");
        }

        public void OnItemFound(ItemFoundPage page) => _plugin.StartCoroutine(Dismiss(page, () => page.Receive(), "item found"));

        public void OnCharacterFound(CharacterFoundPage page) => _plugin.StartCoroutine(CharacterFound(page));

        private IEnumerator CharacterFound(CharacterFoundPage page)
        {
            yield return new WaitForSecondsRealtime(Plugin.MenuDelayS.Value);
            if (!CanAutomate() || page == null) yield break;
            page.Reveal();
            yield return new WaitForSecondsRealtime(1.5f);
            if (!CanAutomate() || page == null || !page.gameObject.activeInHierarchy) yield break;
            page.CollectCharacter();
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
            yield return new WaitForSecondsRealtime(2f);   // GameOverPage computes _stageComplete in OnIntroEnded ~1 s after showing
            if (page != null && page.gameObject.activeInHierarchy && page._hasRevives && CanAutomate())
            {
                // GameOverPage.OnShowStart sets _hasRevives = GM.Core.HasAPlayerGotRevivals() before this
                // coroutine can observe the page; Revive() has no other precondition (it just iterates
                // GM.Core.AllPlayers, spends a revival on each one that has PRevivals() >= 1, and plays the
                // revive animation), so calling it directly is safe (verified in decompiled GameOverPage.cs).
                Plugin.Log.LogInfo("game over: reviving");
                page.Revive();
                yield break;
            }
            _runInProgress = false;
            RunsFinished++;
            // Telemetry below is deliberately not gated by automation: a run that ended is counted and reported either way.
            var gm = GM.Core;
            var p = gm?.Player;
            var summary = new JObject
            {
                ["character"] = p?.CharacterType.ToString(),
                ["stage"] = gm?.PlayerOptions?.Config?.SelectedStage.ToString(),
                ["seconds"] = gm != null ? Mathf.RoundToInt(gm.SurvivedSeconds) : 0,
                ["level"] = p?.Level ?? 0,
                ["kills"] = ReadKills(),
                ["stage_complete"] = page != null && page._stageComplete,
            };
            Plugin.Log.LogInfo($"game over: {summary.ToString(Newtonsoft.Json.Formatting.None)}");
            if (_t.Connected)
                _t.Request(new JObject { ["type"] = "event", ["event"] = "game_over", ["summary"] = summary }, 2f, _ => { }, () => { });
            yield return new WaitForSecondsRealtime(0.5f);
            if (!CanAutomate() || page == null || !page.gameObject.activeInHierarchy) yield break;
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

        public void OnPause(PausePage page) => _plugin.StartCoroutine(Pause(page));

        private IEnumerator Pause(PausePage page)
        {
            yield return new WaitForSecondsRealtime(Plugin.MenuDelayS.Value);
            if (!CanAutomate() || page == null || !page.gameObject.activeInHierarchy) yield break;
            Plugin.Log.LogInfo("pause: resuming");
            page.ReturnToGame();
        }
    }
}
