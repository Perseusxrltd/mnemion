const { build } = require('./package.json')
// Unique feeds prevent x64/ARM artifacts from overwriting each other's metadata.
module.exports = {
  ...build,
  publish: [{ provider: 'github', owner: 'Perseusxrltd', repo: 'mnemion',
    releaseType: 'release', channel: `latest-${process.arch}` }],
}
