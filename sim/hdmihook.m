// Simulator test hook: force-enable YouTube's built-in fullscreen-HDMI service and log its activity.
#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#import <objc/message.h>

#define HLOG(fmt, ...) NSLog(@"[HDMIHOOK] " fmt, ##__VA_ARGS__)

static IMP swizzle(const char *cls, const char *sel, IMP newImp) {
    Class c = objc_getClass(cls);
    if (!c) { HLOG(@"class %s not found", cls); return NULL; }
    Method m = class_getInstanceMethod(c, sel_registerName(sel));
    if (!m) { HLOG(@"method %s %s not found", cls, sel); return NULL; }
    IMP orig = method_setImplementation(m, newImp);
    HLOG(@"hooked -[%s %s]", cls, sel);
    return orig;
}

static IMP orig_flag_impl, orig_flag_hot;
static BOOL flag_yes(id self, SEL _cmd) { HLOG(@"%@ -> YES (forced)", NSStringFromSelector(_cmd)); return YES; }

static IMP orig_enable, orig_setViewToMirror, orig_detect, orig_didConnect, orig_stop, orig_prepare;
static void my_enable(id self, SEL _cmd, id pc) {
    HLOG(@"enableHDMIPlayback: %@ screens=%lu", pc, (unsigned long)[UIScreen screens].count);
    ((void(*)(id,SEL,id))orig_enable)(self, _cmd, pc);
    HLOG(@"after enable: secondScreen=%@ secondWindow=%@ renderingView=%@",
         [self valueForKey:@"secondScreen"], [self valueForKey:@"secondWindow"], [self valueForKey:@"renderingView"]);
}
static BOOL my_setViewToMirror(id self, SEL _cmd, id view, id pc) {
    BOOL r = ((BOOL(*)(id,SEL,id,id))orig_setViewToMirror)(self, _cmd, view, pc);
    HLOG(@"setViewToMirror:%@ playbackController:%@ -> %d", view, pc, r);
    return r;
}
static void my_detect(id self, SEL _cmd) {
    ((void(*)(id,SEL))orig_detect)(self, _cmd);
    HLOG(@"detectExternalScreen: screens=%@ -> secondScreen=%@", [UIScreen screens], [self valueForKey:@"secondScreen"]);
}
static __weak id g_lastPC;
static IMP orig_didActivate;
static void my_didActivate(id self, SEL _cmd, id pc, id video) {
    g_lastPC = pc; HLOG(@"didActivateVideo pc=%@", pc);
    ((void(*)(id,SEL,id,id))orig_didActivate)(self, _cmd, pc, video);
}
static void my_didConnect(id self, SEL _cmd, id note) {
    HLOG(@"externalScreenDidConnect: %@", note);
    ((void(*)(id,SEL,id))orig_didConnect)(self, _cmd, note);
    id pc = g_lastPC;
    if (pc) {
        dispatch_async(dispatch_get_main_queue(), ^{
            HLOG(@"connect -> enableHDMIPlayback: %@ (added by hook)", pc);
            ((void(*)(id,SEL,id))objc_msgSend)(self, sel_registerName("enableHDMIPlayback:"), pc);
        });
    }
}
static void my_stop(id self, SEL _cmd) { HLOG(@"stopMirroring"); ((void(*)(id,SEL))orig_stop)(self, _cmd); }
static void my_prepare(id self, SEL _cmd) {
    ((void(*)(id,SEL))orig_prepare)(self, _cmd);
    HLOG(@"prepareIfNeeded done, prepared=%@", [self valueForKey:@"prepared"]);
}

// --- error diagnostics ---
static IMP orig_err[8];
#define ERRHOOK(idx, cls, sel) \
    static void err_##idx(id self, SEL _cmd, id a) { HLOG(@"ERR %s %@: %@", cls, NSStringFromSelector(_cmd), a); ((void(*)(id,SEL,id))orig_err[idx])(self,_cmd,a); }
#define ERRHOOK2(idx, cls, sel) \
    static void err2_##idx(id self, SEL _cmd, id a, id b) { HLOG(@"ERR %s %@: %@ / %@", cls, NSStringFromSelector(_cmd), a, b); ((void(*)(id,SEL,id,id))orig_err[idx])(self,_cmd,a,b); }
ERRHOOK(0, "YTLocalPlaybackController", "failWithError:")
ERRHOOK(1, "MLHAMQueuePlayer", "failWithError:")
ERRHOOK(2, "MLHAMQueuePlayer", "terminatePlayerWithError:")
ERRHOOK(3, "YTSingleVideoController", "failWithError:")
ERRHOOK(4, "MLHAMQueuePlayer", "onNonFatalErrorEvent:")
ERRHOOK2(5, "YTPlayerViewController", "playbackController:didFailWithError:")
ERRHOOK2(6, "MLHAMQueuePlayer", "playerItem:didFailWithError:")
ERRHOOK(7, "MLAVPlayer", "failWithError:")

#include <execinfo.h>
#include <dlfcn.h>
#include <mach-o/dyld.h>
static IMP orig_nserror_init;
static id my_nserror_init(id self, SEL _cmd, NSString *domain, NSInteger code, NSDictionary *ui) {
    id r = ((id(*)(id,SEL,NSString*,NSInteger,NSDictionary*))orig_nserror_init)(self, _cmd, domain, code, ui);
    if ([[ui description] rangeOfString:@"simulator"].location != NSNotFound || [[domain description] rangeOfString:@"simulator"].location != NSNotFound) {
        void *bt[24]; int n = backtrace(bt, 24);
        NSMutableString *s = [NSMutableString string];
        for (int i = 0; i < n; i++) {
            Dl_info info; if (dladdr(bt[i], &info) && info.dli_fbase) {
                const char *img = strrchr(info.dli_fname, '/'); img = img ? img+1 : info.dli_fname;
                [s appendFormat:@" %s+0x%lx", img, (unsigned long)((char*)bt[i] - (char*)info.dli_fbase)];
            }
        }
        HLOG(@"NSError domain=%@ code=%ld ui=%@ bt:%@", domain, (long)code, ui, s);
    }
    return r;
}

static BOOL no_metal(id self, SEL _cmd) { HLOG(@"deviceSupportsMetal -> NO (forced, simulator)"); return NO; }
__attribute__((constructor)) static void init(void) {
    { Class mc = objc_getMetaClass("HAMMetalPixelBufferRenderingView");
      Method m = mc ? class_getClassMethod(objc_getClass("HAMMetalPixelBufferRenderingView"), sel_registerName("deviceSupportsMetal")) : NULL;
      if (m) { method_setImplementation(m, (IMP)no_metal); HLOG(@"hooked +[HAMMetalPixelBufferRenderingView deviceSupportsMetal]"); } else HLOG(@"deviceSupportsMetal not found"); }
    orig_nserror_init = swizzle("NSError", "initWithDomain:code:userInfo:", (IMP)my_nserror_init);
    orig_err[0] = swizzle("YTLocalPlaybackController", "failWithError:", (IMP)err_0);
    orig_err[1] = swizzle("MLHAMQueuePlayer", "failWithError:", (IMP)err_1);
    orig_err[2] = swizzle("MLHAMQueuePlayer", "terminatePlayerWithError:", (IMP)err_2);
    orig_err[3] = swizzle("YTSingleVideoController", "failWithError:", (IMP)err_3);
    orig_err[4] = swizzle("MLHAMQueuePlayer", "onNonFatalErrorEvent:", (IMP)err_4);
    orig_err[5] = swizzle("YTPlayerViewController", "playbackController:didFailWithError:", (IMP)err2_5);
    orig_err[6] = swizzle("MLHAMQueuePlayer", "playerItem:didFailWithError:", (IMP)err2_6);
    orig_err[7] = swizzle("MLAVPlayer", "failWithError:", (IMP)err_7);
    HLOG(@"loaded in %@", [[NSBundle mainBundle] bundleIdentifier]);
    // 21.35.3
    orig_flag_impl = swizzle("YTHotConfigIosClientGlobalConfigImpl", "fullscreenHdmiHamplayer", (IMP)flag_yes);
    // 20.10.4 (and still present in 21.x, unused there)
    orig_flag_hot = swizzle("YTHotConfig", "iosClientGlobalConfigFullscreenHdmiHamplayer", (IMP)flag_yes);

    orig_prepare = swizzle("YTHDMIServiceImpl", "prepareIfNeeded", (IMP)my_prepare);
    orig_enable = swizzle("YTHDMIServiceImpl", "enableHDMIPlayback:", (IMP)my_enable);
    orig_setViewToMirror = swizzle("YTHDMIServiceImpl", "setViewToMirror:playbackController:", (IMP)my_setViewToMirror);
    orig_detect = swizzle("YTHDMIServiceImpl", "detectExternalScreen", (IMP)my_detect);
    orig_didConnect = swizzle("YTHDMIServiceImpl", "externalScreenDidConnect:", (IMP)my_didConnect);
    orig_stop = swizzle("YTHDMIServiceImpl", "stopMirroring", (IMP)my_stop);
    orig_didActivate = swizzle("YTHDMIServicePlaybackObserverImpl", "playerViewController:didActivateVideo:", (IMP)my_didActivate);
    if (!orig_didActivate) orig_didActivate = swizzle("YTHDMIServicePlaybackObserverImpl", "playbackController:didActivateVideo:", (IMP)my_didActivate);

    [[NSNotificationCenter defaultCenter] addObserverForName:UIScreenDidConnectNotification object:nil queue:nil usingBlock:^(NSNotification *n) {
        HLOG(@"UIScreenDidConnectNotification %@ screens=%lu", n.object, (unsigned long)[UIScreen screens].count);
    }];
    [[NSNotificationCenter defaultCenter] addObserverForName:UIScreenDidDisconnectNotification object:nil queue:nil usingBlock:^(NSNotification *n) {
        HLOG(@"UIScreenDidDisconnectNotification %@", n.object);
    }];
}
