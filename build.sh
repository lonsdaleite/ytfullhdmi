#!/bin/sh
# Build YTFullHDMI.dylib for arm64 iOS devices (no Theos / Substrate required).
set -e
cd "$(dirname "$0")"
mkdir -p out
xcrun -sdk iphoneos clang -arch arm64 -miphoneos-version-min=15.0 -fobjc-arc -dynamiclib \
    -framework Foundation -framework UIKit \
    -install_name @rpath/YTFullHDMI.dylib \
    -o out/YTFullHDMI.dylib YTFullHDMI.m
echo "built out/YTFullHDMI.dylib"
