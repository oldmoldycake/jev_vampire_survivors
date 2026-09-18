#!/usr/bin/env bash
# Decompiles the game's logic assembly into ./decompiled (git-ignored) for reading method bodies.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.dotnet:$HOME/.dotnet/tools:$PATH"
export DOTNET_CLI_TELEMETRY_OPTOUT=1
GAME_DIR="${GAME_DIR:-$HOME/.local/share/Steam/steamapps/common/Vampire Survivors}"
M="$GAME_DIR/VampireSurvivors_Data/Managed"
# Validate before the global tool install and before destroying any previous output.
[ -f "$M/VampireSurvivors.Runtime.dll" ] || {
  echo "game assembly not found: $M/VampireSurvivors.Runtime.dll (set GAME_DIR)" >&2; exit 1; }
command -v ilspycmd >/dev/null || dotnet tool install -g ilspycmd --version 9.1.0.7988
rm -rf decompiled && mkdir -p decompiled
ilspycmd "$M/VampireSurvivors.Runtime.dll" -p -o decompiled -r "$M"
echo "decompiled to ./decompiled ($(find decompiled -name '*.cs' | wc -l) files)"
