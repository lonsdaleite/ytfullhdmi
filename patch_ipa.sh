#!/bin/sh
# Inject out/YTFullHDMI.dylib into a decrypted (or already tweaked) YouTube IPA.
# usage: ./patch_ipa.sh <input.ipa> [output.ipa]
# The result is unsigned: sign it with your usual sideload tool (eSign / SideStore / TrollStore).
set -e
cd "$(dirname "$0")"
IN="$1"; OUT="${2:-out/$(basename "${IN%.ipa}")_YTFullHDMI.ipa}"
[ -f "$IN" ] || { echo "no input ipa"; exit 1; }
[ -f out/YTFullHDMI.dylib ] || ./build.sh
W="$(mktemp -d)"
unzip -q "$IN" -d "$W"
APP="$(ls -d "$W"/Payload/*.app | head -1)"
mkdir -p "$APP/Frameworks"
cp out/YTFullHDMI.dylib "$APP/Frameworks/"
python3 insert_dylib.py "$APP/$(/usr/libexec/PlistBuddy -c 'Print CFBundleExecutable' "$APP/Info.plist")" @rpath/YTFullHDMI.dylib
rm -rf "$APP/_CodeSignature"
mkdir -p "$(dirname "$OUT")"
OUT_ABS="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
rm -f "$OUT_ABS"
(cd "$W" && zip -qr "$OUT_ABS" Payload)
rm -rf "$W"
echo "wrote $OUT"
