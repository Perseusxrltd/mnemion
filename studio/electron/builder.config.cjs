const { build } = require('./package.json')
// GitHub supplies absent secrets as empty strings. electron-builder interprets
// an empty CSC_LINK as the working directory instead of an absent certificate.
for (const name of ['CSC_LINK', 'CSC_KEY_PASSWORD', 'APPLE_ID', 'APPLE_APP_SPECIFIC_PASSWORD', 'APPLE_TEAM_ID']) {
  if (process.env[name] === '') delete process.env[name]
}
// Unique feeds prevent x64/ARM artifacts from overwriting each other's metadata.
module.exports = {
  ...build,
  publish: [{ provider: 'github', owner: 'Perseusxrltd', repo: 'mnemion',
    releaseType: 'release', channel: `latest-${process.arch}` }],
}
