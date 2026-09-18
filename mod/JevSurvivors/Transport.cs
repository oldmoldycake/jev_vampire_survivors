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
