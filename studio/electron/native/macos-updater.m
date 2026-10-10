// Mnemion's control adapter for Sparkle 2.10.0. Sparkle owns archive validation,
// extraction, replacement and relaunch; this process owns no custom installer.
#import <Cocoa/Cocoa.h>
#import <Sparkle/Sparkle.h>
#include <signal.h>
#include <unistd.h>

static const uint64_t MaximumArchiveBytes = 1024ULL * 1024ULL * 1024ULL;

static void Emit(NSDictionary *event) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:event options:0 error:NULL];
    if (data != nil && data.length <= 2048) {
        fwrite(data.bytes, 1, data.length, stdout);
        fputc('\n', stdout);
        fflush(stdout);
    }
}

static BOOL StableVersion(NSString *version) {
    if (![version isKindOfClass:[NSString class]] || version.length > 32) return NO;
    NSRegularExpression *pattern = [NSRegularExpression
        regularExpressionWithPattern:@"^[0-9]+\\.[0-9]+\\.[0-9]+$" options:0 error:NULL];
    return [pattern numberOfMatchesInString:version options:0
        range:NSMakeRange(0, version.length)] == 1;
}

@interface MnemionUpdateDriver : NSObject <SPUUserDriver, SPUUpdaterDelegate>
@property(nonatomic, strong) SPUUpdater *updater;
@property(nonatomic, strong) NSBundle *host;
@property(nonatomic, copy) void (^cancelOperation)(void);
@property(nonatomic, copy) void (^readyReply)(SPUUserUpdateChoice);
@property(nonatomic, strong) NSTimer *deadline;
@property(nonatomic, strong) NSMutableData *input;
@property(nonatomic, copy) NSString *version;
@property(nonatomic) uint64_t received;
@property(nonatomic) uint64_t expected;
@property(nonatomic) NSInteger progress;
@property(nonatomic) BOOL cancelled;
@property(nonatomic) BOOL committed;
@property(nonatomic) BOOL errorReported;
- (void)cancel;
- (void)start;
@end

@implementation MnemionUpdateDriver

- (NSString *)feedURLStringForUpdater:(SPUUpdater *)updater {
#ifdef MNEMION_UPDATER_FIXTURE
    return [self.host objectForInfoDictionaryKey:@"SUFeedURL"];
#else
#if defined(__arm64__)
    NSString *architecture = @"arm64";
#else
    NSString *architecture = @"x64";
#endif
    return [NSString stringWithFormat:
        @"https://github.com/Perseusxrltd/mnemion/releases/latest/download/latest-%@-mac.xml",
        architecture];
#endif
}

- (void)fail:(NSString *)reason {
    if (!self.errorReported) {
        self.errorReported = YES;
        Emit(@{@"state": @"error", @"reason": reason});
    }
    [self cancel];
}

- (void)cancel {
    if (self.committed) return;
    self.cancelled = YES;
    if (self.readyReply != nil) {
        void (^reply)(SPUUserUpdateChoice) = self.readyReply;
        self.readyReply = nil;
        // Skip at this stage cancels installation; Dismiss would install on quit.
        reply(SPUUserUpdateChoiceSkip);
    } else if (self.cancelOperation != nil) {
        void (^cancellation)(void) = self.cancelOperation;
        self.cancelOperation = nil;
        cancellation();
    }
}

- (void)command:(NSString *)command {
    if ([command isEqualToString:@"cancel"]) {
        [self cancel];
    } else if ([command isEqualToString:@"install"] && !self.cancelled
               && !self.committed && self.readyReply != nil) {
        // Only Electron may send this, after checking focus, drafts, jobs and idle time.
        self.committed = YES;
        [self.deadline invalidate];
        self.deadline = nil;
        void (^reply)(SPUUserUpdateChoice) = self.readyReply;
        self.readyReply = nil;
        Emit(@{@"state": @"installing"});
        reply(SPUUserUpdateChoiceInstall);
    } else {
        [self fail:@"invalid-control-message"];
    }
}

- (void)start {
    self.input = [NSMutableData data];
    self.progress = -1;
    self.updater = [[SPUUpdater alloc] initWithHostBundle:self.host
        applicationBundle:self.host userDriver:self delegate:self];
    self.updater.userAgentString = @"Mnemion Studio updater";
    // Scheduling, consent and preferences belong to Electron, including managed policy.
    // Info.plist disables Sparkle's independent scheduling and profile collection.
    NSFileHandle *input = [NSFileHandle fileHandleWithStandardInput];
    __weak MnemionUpdateDriver *weakSelf = self;
    input.readabilityHandler = ^(NSFileHandle *handle) {
        NSData *data = [handle availableData];
        if (data.length == 0) handle.readabilityHandler = nil;
        dispatch_async(dispatch_get_main_queue(), ^{
            MnemionUpdateDriver *driver = weakSelf;
            if (driver == nil) return;
            if (data.length == 0) {
                [driver cancel];
                return;
            }
            if (driver.input.length + data.length > 128) {
                [driver fail:@"control-message-too-large"];
                return;
            }
            [driver.input appendData:data];
            NSData *newline = [@"\n" dataUsingEncoding:NSUTF8StringEncoding];
            for (NSUInteger count = 0; count < 8; count++) {
                NSRange separator = [driver.input rangeOfData:newline options:0
                    range:NSMakeRange(0, driver.input.length)];
                if (separator.location == NSNotFound) break;
                NSData *line = [driver.input subdataWithRange:NSMakeRange(0, separator.location)];
                [driver.input replaceBytesInRange:NSMakeRange(0, separator.location + 1)
                    withBytes:NULL length:0];
                [driver command:[[NSString alloc] initWithData:line
                    encoding:NSUTF8StringEncoding]];
            }
        });
    };
    self.deadline = [NSTimer scheduledTimerWithTimeInterval:20 * 60 repeats:NO
        block:^(NSTimer *timer) { [weakSelf fail:@"update-time-limit"]; }];
    NSError *error = nil;
    if (![self.updater startUpdater:&error]) {
        Emit(@{@"state": @"error", @"reason": @"configuration", @"code": @(error.code)});
        exit(EXIT_FAILURE);
    }
    [self.updater checkForUpdates];
}

- (BOOL)updaterShouldPromptForPermissionToCheckForUpdates:(SPUUpdater *)updater {
    return NO;
}
- (void)showUpdatePermissionRequest:(SPUUpdatePermissionRequest *)request
    reply:(void (^)(SUUpdatePermissionResponse *))reply {
    reply([[SUUpdatePermissionResponse alloc] initWithAutomaticUpdateChecks:NO
        sendSystemProfile:NO]);
}
- (BOOL)updater:(SPUUpdater *)updater mayPerformUpdateCheck:(SPUUpdateCheck)check
    error:(NSError **)error {
    NSFileManager *files = [NSFileManager defaultManager];
    BOOL writable = geteuid() != 0 && [files isWritableFileAtPath:self.host.bundlePath]
        && [files isWritableFileAtPath:self.host.bundlePath.stringByDeletingLastPathComponent];
    if (!writable || self.cancelled) {
        if (error != NULL) *error = [NSError errorWithDomain:@"MnemionUpdater" code:1
            userInfo:@{NSLocalizedDescriptionKey: @"Install the app in a writable Applications folder."}];
        return NO;
    }
    return YES;
}
- (BOOL)updater:(SPUUpdater *)updater shouldProceedWithUpdate:(SUAppcastItem *)item
    updateCheck:(SPUUpdateCheck)check error:(NSError **)error {
    NSURL *url = item.fileURL;
    BOOL allowed = StableVersion(item.versionString) && !self.cancelled
        && !item.informationOnlyUpdate && !item.deltaUpdate
        && [item.installationType isEqualToString:@"application"]
        && item.contentLength > 0 && item.contentLength <= MaximumArchiveBytes;
#ifdef MNEMION_UPDATER_FIXTURE
    NSURL *feed = [NSURL URLWithString:[self feedURLStringForUpdater:updater]];
    allowed = allowed && [url.scheme isEqualToString:@"http"]
        && [url.host isEqualToString:@"127.0.0.1"] && [url.port isEqual:feed.port];
#else
#if defined(__arm64__)
    NSString *architecture = @"arm64";
#else
    NSString *architecture = @"x64";
#endif
    NSString *expected = [NSString stringWithFormat:
        @"/Perseusxrltd/mnemion/releases/download/v%@/Mnemion-Studio-%@-macos-%@.zip",
        item.versionString, item.versionString, architecture];
    allowed = allowed && [url.scheme isEqualToString:@"https"]
        && [url.host isEqualToString:@"github.com"] && [url.path isEqualToString:expected]
        && url.user == nil && url.password == nil && url.query == nil
        && url.fragment == nil && url.port == nil;
#endif
    if (!allowed) {
        if (error != NULL) *error = [NSError errorWithDomain:@"MnemionUpdater" code:2
            userInfo:@{NSLocalizedDescriptionKey: @"The update does not match the release policy."}];
    }
    return allowed;
}
- (BOOL)updater:(SPUUpdater *)updater shouldDownloadReleaseNotesForUpdate:(SUAppcastItem *)item {
    return NO; // No rendering or navigation to feed-supplied content.
}
- (void)showUserInitiatedUpdateCheckWithCancellation:(void (^)(void))cancellation {
    self.cancelOperation = cancellation;
    Emit(@{@"state": @"checking"});
    if (self.cancelled) [self cancel];
}
- (void)showUpdateFoundWithAppcastItem:(SUAppcastItem *)item
    state:(SPUUserUpdateState *)state reply:(void (^)(SPUUserUpdateChoice))reply {
    self.cancelOperation = nil;
    self.version = item.versionString;
    if (self.cancelled || item.informationOnlyUpdate) {
        reply(SPUUserUpdateChoiceSkip);
    } else if (state.stage == SPUUserUpdateStageInstalling) {
        // A resumed installer must obey the same safe-restart control as a new one.
        [self showReadyToInstallAndRelaunch:reply];
    } else {
        Emit(@{@"state": @"downloading", @"version": self.version});
        reply(SPUUserUpdateChoiceInstall);
    }
}
- (void)showDownloadInitiatedWithCancellation:(void (^)(void))cancellation {
    self.cancelOperation = cancellation;
    self.received = 0;
    if (self.cancelled) [self cancel];
}
- (void)showDownloadDidReceiveExpectedContentLength:(uint64_t)length {
    if (length > MaximumArchiveBytes) { [self fail:@"archive-too-large"]; return; }
    self.expected = length;
}
- (void)showDownloadDidReceiveDataOfLength:(uint64_t)length {
    if (length > MaximumArchiveBytes - self.received) {
        [self fail:@"archive-too-large"];
        return;
    }
    self.received += length;
    NSInteger progress = self.expected ? MIN(100, 100 * self.received / self.expected) : 0;
    if (progress != self.progress) {
        self.progress = progress;
        Emit(@{@"state": @"downloading", @"percent": @(progress)});
    }
}
- (void)showDownloadDidStartExtractingUpdate {
    self.cancelOperation = nil;
    Emit(@{@"state": @"verifying"});
}
- (void)showExtractionReceivedProgress:(double)progress {}
- (void)showReadyToInstallAndRelaunch:(void (^)(SPUUserUpdateChoice))reply {
    self.cancelOperation = nil;
    self.readyReply = reply;
    if (self.cancelled) {
        [self cancel];
        return;
    }
    [self.deadline invalidate];
    __weak MnemionUpdateDriver *weakSelf = self;
    self.deadline = [NSTimer scheduledTimerWithTimeInterval:24 * 60 * 60 repeats:NO
        block:^(NSTimer *timer) { [weakSelf cancel]; }];
    Emit(@{@"state": @"ready", @"version": self.version ?: @""});
}
- (void)showInstallingUpdateWithApplicationTerminated:(BOOL)terminated
    retryTerminatingApplication:(void (^)(void))retry {}
- (void)showUpdateInstalledAndRelaunched:(BOOL)relaunched
    acknowledgement:(void (^)(void))acknowledgement {
    Emit(@{@"state": @"installed", @"relaunched": @(relaunched)});
    acknowledgement();
}
- (void)showUpdateNotFoundWithError:(NSError *)error
    acknowledgement:(void (^)(void))acknowledgement {
    Emit(@{@"state": @"current"});
    acknowledgement();
}
- (void)showUpdaterError:(NSError *)error acknowledgement:(void (^)(void))acknowledgement {
    if (!self.cancelled) {
        self.errorReported = YES;
        Emit(@{@"state": @"error", @"reason": @"sparkle", @"code": @(error.code)});
    }
    acknowledgement();
}
- (void)updater:(SPUUpdater *)updater
    didFinishUpdateCycleForUpdateCheck:(SPUUpdateCheck)check error:(NSError *)error {
    [self.deadline invalidate];
    if (self.cancelled && !self.errorReported) Emit(@{@"state": @"cancelled"});
    if (error != nil && !self.errorReported && !self.cancelled && error.code != SUNoUpdateError) {
        Emit(@{@"state": @"error", @"reason": @"sparkle", @"code": @(error.code)});
    }
    exit(error != nil && error.code != SUNoUpdateError && !self.cancelled ? EXIT_FAILURE : EXIT_SUCCESS);
}
- (void)showUpdateReleaseNotesWithDownloadData:(SPUDownloadData *)data {}
- (void)showUpdateReleaseNotesFailedToDownloadWithError:(NSError *)error {}
- (void)dismissUpdateInstallation {}
- (void)showUpdateInFocus {}
@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        signal(SIGPIPE, SIG_IGN);
        // Resolve only our containing bundle; no user-supplied executable or bundle path.
        NSString *executable = [[[NSProcessInfo processInfo] arguments][0]
            stringByResolvingSymlinksInPath];
        NSString *path = executable.stringByDeletingLastPathComponent
            .stringByDeletingLastPathComponent.stringByDeletingLastPathComponent;
        NSBundle *host = [NSBundle bundleWithPath:path];
#ifdef MNEMION_UPDATER_FIXTURE
        BOOL expected = [host.bundleIdentifier hasPrefix:@"com.perseusxr.mnemion.update-probe."];
#else
        BOOL expected = [host.bundleIdentifier isEqualToString:@"com.perseusxr.mnemion-studio"];
#endif
        NSString *publicKey = [host objectForInfoDictionaryKey:@"SUPublicEDKey"];
        if (argc != 1 || !expected || !StableVersion([host objectForInfoDictionaryKey:@"CFBundleVersion"])
            || ![publicKey isKindOfClass:[NSString class]]
            || [[NSData alloc] initWithBase64EncodedString:
                publicKey options:0].length != 32) {
            Emit(@{@"state": @"error", @"reason": @"configuration"});
            return EXIT_FAILURE;
        }
        MnemionUpdateDriver *driver = [MnemionUpdateDriver new];
        driver.host = host;
        [driver start];
        [[NSRunLoop currentRunLoop] run];
    }
    return EXIT_SUCCESS;
}
