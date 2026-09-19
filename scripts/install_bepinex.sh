#!/usr/bin/env bash
# Installs BepInEx 5 (Linux x64) into the Vampire Survivors folder. Safe to re-run.
set -euo pipefail
GAME_DIR="${GAME_DIR:-$HOME/.local/share/Steam/steamapps/common/Vampire Survivors}"

# This installs the Linux Mono flavour of BepInEx 5. Unpacking it into the Windows IL2CPP build
# produces a game that loads nothing and a folder that is hard to untangle afterwards.
if [ -d "$GAME_DIR" ] && [ ! -d "$GAME_DIR/VampireSurvivors_Data/Managed" ] && [ -d "$GAME_DIR/VampireSurvivors_Data/il2cpp_data" ]; then
  echo "$GAME_DIR holds the Windows IL2CPP build, not the Linux Mono build." >&2
  echo "BepInEx 5 Linux cannot load it. Restore the Linux build first:" >&2
  echo "  Steam -> Vampire Survivors -> Properties -> Installed Files -> Verify integrity of game files" >&2
  exit 1
fi
PINNED_VER="5.4.23.5"
# sha256 of BepInEx_linux_x64_5.4.23.5.zip, as published by GitHub for that release asset.
PINNED_SHA256="e538560be65739f562519ab518a75f9c65b3f57f87457403ae7cde683c12dab7"
VER="${BEPINEX_VERSION:-$PINNED_VER}"
URL="https://github.com/BepInEx/BepInEx/releases/download/v${VER}/BepInEx_linux_x64_${VER}.zip"

# This archive is unpacked into the game folder and its run_bepinex.sh then executes on every
# launch, so verify what arrived rather than trusting the transport alone.
if [ -n "${BEPINEX_SHA256:-}" ]; then
  want="$BEPINEX_SHA256"
elif [ "$VER" = "$PINNED_VER" ]; then
  want="$PINNED_SHA256"
elif [ "${BEPINEX_ALLOW_UNVERIFIED:-}" = "1" ]; then
  want=""
  echo "WARNING: installing BepInEx $VER with no checksum verification" >&2
else
  echo "no pinned checksum for BepInEx $VER (this script pins $PINNED_VER)." >&2
  echo "Pass BEPINEX_SHA256=<sha256> to verify it, or BEPINEX_ALLOW_UNVERIFIED=1 to skip." >&2
  exit 1
fi

[ -d "$GAME_DIR" ] || { echo "game dir not found: $GAME_DIR" >&2; exit 1; }
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
echo "downloading $URL"
curl -sSL "$URL" -o "$tmp/bepinex.zip"
if [ -n "$want" ]; then
  echo "$want  $tmp/bepinex.zip" | sha256sum -c - >/dev/null || {
    echo "checksum mismatch for $URL -- refusing to install" >&2
    echo "  expected $want" >&2
    echo "  got      $(sha256sum "$tmp/bepinex.zip" | cut -d" " -f1)" >&2
    exit 1; }
  echo "checksum ok"
fi
unzip -o -q "$tmp/bepinex.zip" -d "$GAME_DIR"
chmod u+x "$GAME_DIR/run_bepinex.sh"
sed -i 's/^executable_name=.*/executable_name="VampireSurvivors.exe"/' "$GAME_DIR/run_bepinex.sh"
grep -q 'executable_name="VampireSurvivors.exe"' "$GAME_DIR/run_bepinex.sh"
mkdir -p "$GAME_DIR/BepInEx/plugins"
echo "BepInEx $VER installed in: $GAME_DIR"
echo
echo "NOW: Steam -> Vampire Survivors -> Properties -> Launch Options, set exactly:"
echo '    ./run_bepinex.sh %command%'
