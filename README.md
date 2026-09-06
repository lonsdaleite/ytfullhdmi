# YTFullHDMI

Fullscreen video output from the iOS YouTube app to a wired external display (USB-C / Lightning → HDMI).

Made first of all for USB-C AR glasses such as XREAL, Viture, Rokid: plugged into an iPhone they only
get system mirroring, so YouTube shows up as a small letterboxed phone screen with the UI around it.
With this tweak the glasses get the video alone, full frame, while the phone keeps the controls. Any
HDMI monitor or TV behind a USB-C adapter behaves the same way.

## How it works

YouTube already contains the feature. `YTHDMIServiceImpl` creates a `UIWindow` on the external
`UIScreen` and moves the player's rendering view (`MLHAMAspectPreservingView`) into it, so the
monitor shows only the video while the phone keeps the UI and controls. The service is gated by the
server experiment flag `fullscreenHdmiHamplayer` (experiment id 45372440), which is off unless the
account is in the experiment.

`YTFullHDMI.dylib` does two things:

- forces the flag getter to return `YES`
  (`-[YTHotConfigIosClientGlobalConfigImpl fullscreenHdmiHamplayer]` on YouTube 21.x,
  `-[YTHotConfig iosClientGlobalConfigFullscreenHdmiHamplayer]` on 20.x);
- returns `NO` from `-[MLAudioSession outputRouteUsesHDMI]`. With a wired HDMI audio route
  `MLHAMQueuePlayer maybeSwitchToAVPlayer` reloads playback onto the AVPlayer/HLS path, which has no
  stream for most videos and fails with "No stream"; keeping the HAM player avoids that;
- calls `-[YTHDMIServiceImpl enableHDMIPlayback:]` as soon as a display is connected during playback.
  Stock code only records the screen on connect and starts mirroring on the next video activation.

It logs with the `[YTFullHDMI]` prefix (Console.app, filter by process `YouTube`).

The dylib uses plain ObjC runtime swizzling, no Substrate / Theos.

Verified in the iOS Simulator (Xcode 26.6, iOS 26.5) with YouTube 21.35.3 and a simulated
1920×1080 external display: video renders fullscreen in the external window, returns to the phone on
disconnect, and moves immediately when the display is connected mid-playback. YouTube 20.10.4 hangs at
the splash screen in the simulator, so it is untested there; the hooked methods exist and the
`YTHDMIServiceImpl` code is identical.

## Build and inject

```sh
./build.sh                                  # -> out/YTFullHDMI.dylib
./patch_ipa.sh /path/to/YouTube.ipa         # -> out/<name>_YTFullHDMI.ipa (unsigned)
```

`patch_ipa.sh` copies the dylib into `Frameworks/` and adds a weak `LC_LOAD_DYLIB` to the main
binary (`insert_dylib.py`). Sign the result with eSign / SideStore / TrollStore as usual. The input
can be a stock decrypted IPA or an already tweaked build (YouTube Plus etc.); with `cyan` the same
thing is `cyan -i in.ipa -o out.ipa -f out/YTFullHDMI.dylib`.

## Layout

- `YTFullHDMI.m` — the tweak.
- `insert_dylib.py`, `patch_ipa.sh`, `build.sh` — packaging.
- `sim/hdmihook.m` — diagnostic build of the hook used for simulator testing. It additionally logs
  every `YTHDMIServiceImpl` call, player errors with backtraces, and forces
  `+[HAMMetalPixelBufferRenderingView deviceSupportsMetal]` to `NO` because `Hamplayer.metallib`
  is compiled for devices and Metal in the simulator rejects it. Not for devices.
- `tools/` — static analysis helpers for the stripped YouTube binary (chained fixups aware):
  - `objcdump.py <binary> [class-regex]` — class dump with IMP addresses;
  - `dis.py <binary> <classdump.txt> <Class:sel|0xaddr>[,…] [maxbytes]` — annotated disassembly
    (resolves `objc_msgSend$sel` stubs, selrefs, cfstrings);
  - `xref.py <binary> <classdump.txt> <sel1,sel2,…>` — callers of selectors;
  - `clsxref.py <binary> <classdump.txt> <Class1,Class2,…>` — where classes are referenced.

## Running a decrypted YouTube in the iOS Simulator

Only needed for testing. Device binaries do not load in the simulator, so:

1. `vtool -arch arm64 -set-build-version 7 17.0 26.4 -replace` on the main binary and on
   `Frameworks/widevine_cdm_secured_ios.framework/widevine_cdm_secured_ios`; delete `PlugIns/`.
2. In `Info.plist` set `CFBundleSupportedPlatforms` to `iPhoneSimulator` and `DTPlatformName` to
   `iphonesimulator`.
3. Remove `_CodeSignature` from the app and the framework, then `codesign -f -s -` the framework
   first and the app second (`--deep` alone leaves the framework signature invalid).
4. `xcrun simctl install <udid> YouTube.app`, then launch with the diagnostic hook:
   `SIMCTL_CHILD_DYLD_INSERT_LIBRARIES=/path/hdmihook.dylib xcrun simctl launch <udid> com.google.ios.youtube`.
   Build the hook with `xcrun -sdk iphonesimulator clang -arch arm64 -mios-simulator-version-min=17.0
   -fobjc-arc -dynamiclib -framework Foundation -framework UIKit -o hdmihook.dylib sim/hdmihook.m`.
5. External display: Simulator menu I/O → External Displays. The simulator does not emulate system
   mirroring, so the external window stays black until the app draws into it.
6. Playback stops after roughly 45 s with `YTMediaError 119` from `MLPlatypusABRLoader`; the server
   cuts the stream without device attestation. Unrelated to the display logic.

Logs: `xcrun simctl spawn <udid> log stream --predicate 'process == "YouTube" AND eventMessage CONTAINS "HDMIHOOK"'`.
