#!/usr/bin/env bash
# Installs BepInEx 5 (Linux x64) into the Vampire Survivors folder. Safe to re-run.
set -euo pipefail
GAME_DIR="${GAME_DIR:-$HOME/.local/share/Steam/steamapps/common/Vampire Survivors}"
VER="${BEPINEX_VERSION:-5.4.23.5}"
URL="https://github.com/BepInEx/BepInEx/releases/download/v${VER}/BepInEx_linux_x64_${VER}.zip"

[ -d "$GAME_DIR" ] || { echo "game dir not found: $GAME_DIR" >&2; exit 1; }
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
echo "downloading $URL"
curl -sSL "$URL" -o "$tmp/bepinex.zip"
unzip -o -q "$tmp/bepinex.zip" -d "$GAME_DIR"
chmod u+x "$GAME_DIR/run_bepinex.sh"
sed -i 's/^executable_name=.*/executable_name="VampireSurvivors.exe"/' "$GAME_DIR/run_bepinex.sh"
grep -q 'executable_name="VampireSurvivors.exe"' "$GAME_DIR/run_bepinex.sh"
mkdir -p "$GAME_DIR/BepInEx/plugins"
echo "BepInEx $VER installed in: $GAME_DIR"
echo
echo "NOW: Steam -> Vampire Survivors -> Properties -> Launch Options, set exactly:"
echo '    ./run_bepinex.sh %command%'
