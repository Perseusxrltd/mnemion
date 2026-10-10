const { build } = require('./package.json')
const sparkle = require('./native/sparkle.json')
// GitHub supplies absent secrets as empty strings. electron-builder interprets
// an empty CSC_LINK as the working directory instead of an absent certificate.
for (const name of ['CSC_LINK', 'CSC_KEY_PASSWORD', 'APPLE_ID', 'APPLE_APP_SPECIFIC_PASSWORD', 'APPLE_TEAM_ID']) {
  if (process.env[name] === '') delete process.env[name]
}
// Unique feeds prevent x64/ARM artifacts from overwriting each other's metadata.
module.exports = {
  ...build,
  mac: {
    ...build.mac,
    identity: '-',
    notarize: false,
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
