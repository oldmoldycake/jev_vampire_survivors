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

# Both builds ship under the same folder name and steamcmd with a platform override will swap one
# for the other in place. Absence of Managed/ is the reliable test: the Mono install also carries
# the Windows IL2CPP payload (GameAssembly.dll, il2cpp_data), so those prove nothing on their own.
if [ ! -f "$GAME_DIR/VampireSurvivors_Data/Managed/VampireSurvivors.Runtime.dll" ]; then
  echo "$GAME_DIR does not hold the Linux Mono build." >&2
  echo "VampireSurvivors_Data/Managed/VampireSurvivors.Runtime.dll is missing, and this plugin is built against it." >&2
  if [ -d "$GAME_DIR/VampireSurvivors_Data/il2cpp_data" ] && [ ! -d "$GAME_DIR/VampireSurvivors_Data/Managed" ]; then
    echo "This looks like the Windows IL2CPP build. Restore the Linux one:" >&2
    echo "  Steam -> Vampire Survivors -> Properties -> Installed Files -> Verify integrity of game files" >&2
  fi
  exit 1
fi
[ -f "$GAME_DIR/BepInEx/core/BepInEx.dll" ] || { echo "BepInEx not installed; run scripts/install_bepinex.sh first" >&2; exit 1; }

dotnet build -c Release "-p:GameDir=$GAME_DIR" "$@"
dest="$GAME_DIR/BepInEx/plugins/JevSurvivors"
mkdir -p "$dest"
cp bin/Release/netstandard2.1/JevSurvivors.dll "$dest/"
echo "deployed $dest/JevSurvivors.dll"
