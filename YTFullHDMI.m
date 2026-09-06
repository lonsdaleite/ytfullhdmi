// YTFullHDMI: enable YouTube's built-in fullscreen playback on a wired external display (HDMI / USB-C).
//
// YouTube ships YTHDMIServiceImpl, which moves the player's rendering view into a UIWindow on the
// external UIScreen. It is gated by the server experiment flag "fullscreenHdmiHamplayer" (id 45372440),
// off by default. This dylib forces the flag on and additionally starts mirroring immediately when a
// display is connected during playback (stock code only reacts on the next video activation).
//
// Build (device):  xcrun -sdk iphoneos clang -arch arm64 -miphoneos-version-min=15.0 -fobjc-arc \
//                  -dynamiclib -framework Foundation -framework UIKit -o YTFullHDMI.dylib YTFullHDMI.m
// Inject with cyan / insert_dylib into YouTube.app, or load as a Substrate tweak (no Substrate needed).

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#import <objc/message.h>
#import <os/log.h>

static IMP swizzle(const char *cls, const char *sel, IMP newImp) {
    Class c = objc_getClass(cls);
    if (!c) return NULL;
    Method m = class_getInstanceMethod(c, sel_registerName(sel));
    if (!m) return NULL;
    return method_setImplementation(m, newImp);
}

// os_log with %{public}s so the text is not redacted as <private> in the device unified log.
#define YLOG(fmt, ...) os_log(OS_LOG_DEFAULT, "[YTFullHDMI] %{public}s", [[NSString stringWithFormat:(fmt), ##__VA_ARGS__] UTF8String])

static BOOL flag_yes(id self, SEL _cmd) { return YES; }

// With a wired HDMI audio route MLHAMQueuePlayer reloads onto the AVPlayer/HLS path
// (maybeSwitchToAVPlayer), which has no stream for most videos ("No stream"). Keep the HAM player.
static BOOL route_no_hdmi(id self, SEL _cmd) { return NO; }

static IMP orig_enable, orig_setViewToMirror;
static void my_enable(id self, SEL _cmd, id pc) {
    YLOG(@"enableHDMIPlayback: %@ screens=%lu", pc, (unsigned long)[UIScreen screens].count);
    ((void (*)(id, SEL, id))orig_enable)(self, _cmd, pc);
}
static BOOL my_setViewToMirror(id self, SEL _cmd, id view, id pc) {
    BOOL r = ((BOOL (*)(id, SEL, id, id))orig_setViewToMirror)(self, _cmd, view, pc);
    YLOG(@"setViewToMirror: %@ -> %d", view, r);
    return r;
}

static __weak id g_lastPlaybackController;
static IMP orig_didActivate, orig_didConnect;

static void my_didActivate(id self, SEL _cmd, id playbackController, id video) {
    g_lastPlaybackController = playbackController;
    ((void (*)(id, SEL, id, id))orig_didActivate)(self, _cmd, playbackController, video);
}

static void my_didConnect(id self, SEL _cmd, id note) {
    YLOG(@"externalScreenDidConnect: %@", [note object]);
    ((void (*)(id, SEL, id))orig_didConnect)(self, _cmd, note);
    id pc = g_lastPlaybackController;
    if (!pc) return;
    dispatch_async(dispatch_get_main_queue(), ^{
        ((void (*)(id, SEL, id))objc_msgSend)(self, sel_registerName("enableHDMIPlayback:"), pc);
    });
}

// Player error logging (diagnostics only): prints the full NSError chain.
static IMP orig_fail[3];
static NSString *errChain(NSError *e) {
    NSMutableString *s = [NSMutableString string];
    for (int i = 0; e && i < 6; i++, e = e.userInfo[NSUnderlyingErrorKey])
        [s appendFormat:@"%@ %@/%ld %@ | ", i ? @"<-" : @"", e.domain, (long)e.code, e.userInfo[NSLocalizedDescriptionKey] ?: e.userInfo[@"HAMErrorDetails"] ?: @""];
    return s;
}
static void my_fail0(id self, SEL _cmd, NSError *e) { YLOG(@"YTSingleVideoController failWithError: %@", errChain(e)); ((void (*)(id, SEL, id))orig_fail[0])(self, _cmd, e); }
static void my_fail1(id self, SEL _cmd, NSError *e) { YLOG(@"MLHAMQueuePlayer terminatePlayerWithError: %@", errChain(e)); ((void (*)(id, SEL, id))orig_fail[1])(self, _cmd, e); }
static void my_fail2(id self, SEL _cmd, id item, NSError *e) { YLOG(@"MLHAMQueuePlayer playerItem:didFailWithError: %@", errChain(e)); ((void (*)(id, SEL, id, id))orig_fail[2])(self, _cmd, item, e); }

__attribute__((constructor)) static void YTFullHDMI_init(void) {
    YLOG(@"loaded");
    orig_fail[0] = swizzle("YTSingleVideoController", "failWithError:", (IMP)my_fail0);
    orig_fail[1] = swizzle("MLHAMQueuePlayer", "terminatePlayerWithError:", (IMP)my_fail1);
    orig_fail[2] = swizzle("MLHAMQueuePlayer", "playerItem:didFailWithError:", (IMP)my_fail2);
    swizzle("MLAudioSession", "outputRouteUsesHDMI", (IMP)route_no_hdmi);
    orig_enable = swizzle("YTHDMIServiceImpl", "enableHDMIPlayback:", (IMP)my_enable);
    orig_setViewToMirror = swizzle("YTHDMIServiceImpl", "setViewToMirror:playbackController:", (IMP)my_setViewToMirror);
    // YouTube >= 21.x
    swizzle("YTHotConfigIosClientGlobalConfigImpl", "fullscreenHdmiHamplayer", (IMP)flag_yes);
    // YouTube 20.x
    swizzle("YTHotConfig", "iosClientGlobalConfigFullscreenHdmiHamplayer", (IMP)flag_yes);

    orig_didActivate = swizzle("YTHDMIServicePlaybackObserverImpl", "playerViewController:didActivateVideo:", (IMP)my_didActivate);
    if (!orig_didActivate)
        orig_didActivate = swizzle("YTHDMIServicePlaybackObserverImpl", "playbackController:didActivateVideo:", (IMP)my_didActivate);
    if (orig_didActivate)
        orig_didConnect = swizzle("YTHDMIServiceImpl", "externalScreenDidConnect:", (IMP)my_didConnect);
}
