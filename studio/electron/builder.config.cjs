const { build } = require('./package.json')
const { join } = require('node:path')
const sparkle = require('./native/sparkle.json')
// GitHub supplies absent secrets as empty strings. electron-builder interprets
// an empty CSC_LINK as the working directory instead of an absent certificate.
for (const name of ['CSC_LINK', 'CSC_KEY_PASSWORD', 'APPLE_ID', 'APPLE_APP_SPECIFIC_PASSWORD', 'APPLE_TEAM_ID']) {
  if (process.env[name] === '') delete process.env[name]
}
// The bundled NSIS decoder cannot extract 7-Zip's automatic ARM64/BCJ2 streams.
// Use the supported single-stream filter; otherwise installers can exit 0 while
// silently omitting executable files. electron-builder upstream issue #9983.
if (process.platform === 'win32') process.env.ELECTRON_BUILDER_7Z_FILTER = 'BCJ'
// Unique feeds prevent x64/ARM artifacts from overwriting each other's metadata.
module.exports = {
  ...build,
  asarUnpack: ['dist/telemetry-private-store.exe'],
  electronFuses: {
    runAsNode: false,
    enableNodeOptionsEnvironmentVariable: false,
    enableNodeCliInspectArguments: false,
    onlyLoadAppFromAsar: true,
    enableEmbeddedAsarIntegrityValidation: process.platform !== 'linux',
  },
  nsis: { ...build.nsis, include: join(__dirname, 'native/windows-installer.nsh') },
  mac: {
    ...build.mac,
    identity: '-',
    notarize: false,
    // These binaries have already been signed ad hoc and inventoried. Signing
    // them again would change the verified native runtime hashes. The outer
    // app signature still seals all of these resources.
    signIgnore: ['Contents/Resources/(engine|postgresql)/'],
    extraFiles: [
      { from: '../../build-tmp/macos-update/MnemionUpdater', to: 'MacOS/MnemionUpdater' },
      { from: '../../build-tmp/macos-update/sparkle/Sparkle.framework', to: 'Frameworks/Sparkle.framework' },
    ],
    extraResources: [{ from: '../../build-tmp/macos-update/build.json', to: 'macos-updater-build.json' }],
    extendInfo: {
      SUFeedURL: `https://github.com/Perseusxrltd/mnemion/releases/latest/download/latest-${process.arch}-mac.xml`,
      SUPublicEDKey: sparkle.publicKey,
      SUEnableAutomaticChecks: false,
      SUAutomaticallyUpdate: false,
      SUEnableSystemProfiling: false,
      SUVerifyUpdateBeforeExtraction: true,
    },
  },
  publish: [{ provider: 'github', owner: 'Perseusxrltd', repo: 'mnemion',
    releaseType: 'release', channel: `latest-${process.arch}` }],
}
