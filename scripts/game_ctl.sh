#!/usr/bin/env bash
# Launch or stop Vampire Survivors through Steam and wait for BepInEx log lines. Verification tooling.
set -euo pipefail
GAME_DIR="${GAME_DIR:-$HOME/.local/share/Steam/steamapps/common/Vampire Survivors}"
EXE="$GAME_DIR/VampireSurvivors.exe"
LOG="$GAME_DIR/BepInEx/LogOutput.log"
game_pids() { for p in /proc/[0-9]*; do [ "$(readlink "$p/exe" 2>/dev/null)" = "$EXE" ] && basename "$p" || true; done; }
case "${1:-}" in
  launch) rm -f "$LOG"; (steam "steam://rungameid/1794680" >/dev/null 2>&1 &); echo "launch requested";;
  wait-log) pat="$2"; t="${3:-120}"; end=$(( $(date +%s) + t ))
    while [ "$(date +%s)" -lt "$end" ]; do
      if [ -f "$LOG" ] && grep -q -E "$pat" "$LOG"; then echo "matched: $pat"; exit 0; fi
      sleep 2
    done; echo "timeout waiting for: $pat" >&2; exit 1;;
  stop) pids=$(game_pids); if [ -n "$pids" ]; then kill $pids; echo "stopped $pids"; else echo "game not running"; fi;;
  status) pids=$(game_pids); if [ -n "$pids" ]; then echo "running: $pids"; else echo "not running"; fi;;
  log) cat "$LOG";;
  *) echo "usage: $0 launch|wait-log PATTERN [TIMEOUT]|stop|status|log" >&2; exit 2;;
esac
