using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using UnityEngine;
using VampireSurvivors.Framework;
using VampireSurvivors.Objects;
using VampireSurvivors.Objects.Characters;
using VampireSurvivors.Objects.Items;
using VampireSurvivors.Objects.Pickups;
using VampireSurvivors.Tools;

namespace JevSurvivors
{
    /// <summary>Sends a raw-state tick at TickHz while a run is active. All numbers are world units relative to the player.</summary>
    public sealed class StateSampler
    {
        private readonly Transport _t;
        private float _next;

        /// <summary>World position at the previous tick, or null when we have none yet (first tick of a session or of a run).
        /// A null here must report a large sentinel distance, never zero, so "we do not know" can't look like "did not move".</summary>
        private static Vector3? _prevPos;

        private const float UnknownMovedSentinel = 999f;

        public StateSampler(Transport t) { _t = t; }

        /// <summary>Forgets the previous tick's position so the first tick of a new run never compares against the last run's final spot.</summary>
        public static void ResetTracking() => _prevPos = null;

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
            float moved = _prevPos.HasValue ? R(Vector3.Distance(pp, _prevPos.Value)) : UnknownMovedSentinel;
            _prevPos = pp;
            Camera cam = stage._mainCamera != null ? stage._mainCamera : Camera.main;
            Bounds b = cam.OrthographicBounds();
            int cap = Plugin.MaxEntities.Value;

            var enemies = new List<(float d, float dx, float dy, EnemyController e)>();
            foreach (var e in stage.GetAllEnemiesInScreenBounds())
            {
                if (e == null || e.IsUnitDead()) continue;
                Vector3 ep = e.transform.position;
                float dx = ep.x - pp.x, dy = ep.y - pp.y;
                enemies.Add((dx * dx + dy * dy, dx, dy, e));
            }

            // GetAllGemsInScreenBounds and GetAllPickupsInScreenBounds share one cache in Stage; keep the gems loop fully drained before the pickups loop.
            var gems = new List<(float d, float dx, float dy, Pickup g)>();
            foreach (var g in stage.GetAllGemsInScreenBounds())
            {
                if (g == null) continue;
                Vector3 gp = g.transform.position;
                float dx = gp.x - pp.x, dy = gp.y - pp.y;
                gems.Add((dx * dx + dy * dy, dx, dy, g));
            }

            var pickups = new List<(float d, float dx, float dy, Pickup p)>();
            foreach (var pk in stage.GetAllPickupsInScreenBounds())
            {
                if (pk == null || pk is Gem) continue;
                Vector3 kp = pk.transform.position;
                float dx = kp.x - pp.x, dy = kp.y - pp.y;
                pickups.Add((dx * dx + dy * dy, dx, dy, pk));
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
                        ["applied_direction"] = string.IsNullOrEmpty(Movement.LastChoice) ? null : Movement.LastChoice,
                        ["moved"] = moved,
                    },
                    ["enemies"] = Nearest(enemies, cap, (dx, dy, e) => new JObject
                    {
                        ["x"] = R(dx), ["y"] = R(dy), ["hp"] = R(e.CurrentHealth()),
                        ["type"] = e.EnemyType.ToString(), ["boss"] = e.IsBoss,
                    }),
                    ["gems"] = Nearest(gems, cap, (dx, dy, g) => new JObject { ["x"] = R(dx), ["y"] = R(dy), ["value"] = R(g.Value) }),
                    ["pickups"] = Nearest(pickups, cap, (dx, dy, pk) => new JObject { ["x"] = R(dx), ["y"] = R(dy), ["kind"] = pk.PickupType.ToString() }),
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

        /// <summary>Sorts by distance and builds JSON for only the nearest `cap` survivors, so entities beyond the cap never allocate a JObject.</summary>
        private static JArray Nearest<T>(List<(float d, float dx, float dy, T item)> items, int cap, Func<float, float, T, JObject> build)
        {
            items.Sort((x, y) => x.d.CompareTo(y.d));
            var arr = new JArray();
            for (int i = 0; i < items.Count && i < cap; i++)
            {
                var it = items[i];
                arr.Add(build(it.dx, it.dy, it.item));
            }
            return arr;
        }

        private static float R(float v) => (float)Math.Round(v, 2);
    }
}
