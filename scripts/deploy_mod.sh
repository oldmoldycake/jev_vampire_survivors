#!/usr/bin/env bash
# Builds the plugin and copies it into the game's BepInEx/plugins folder. Restart the game afterwards.
set -euo pipefail
cd "$(dirname "$0")/../mod/JevSurvivors"
export PATH="$HOME/.dotnet:$PATH"
export DOTNET_CLI_TELEMETRY_OPTOUT=1
GAME_DIR="${GAME_DIR:-$HOME/.local/share/Steam/steamapps/common/Vampire Survivors}"

command -v dotnet >/dev/null || {
  echo "dotnet SDK not found. Install user-locally with:" >&2
  echo '  curl -sSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 8.0' >&2
  exit 1
}
[ -f "$GAME_DIR/BepInEx/core/BepInEx.dll" ] || { echo "BepInEx not installed; run scripts/install_bepinex.sh first" >&2; exit 1; }

dotnet build -c Release "-p:GameDir=$GAME_DIR" "$@"
dest="$GAME_DIR/BepInEx/plugins/JevSurvivors"
mkdir -p "$dest"
cp bin/Release/netstandard2.1/JevSurvivors.dll "$dest/"
echo "deployed $dest/JevSurvivors.dll"
