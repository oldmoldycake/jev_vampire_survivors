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
