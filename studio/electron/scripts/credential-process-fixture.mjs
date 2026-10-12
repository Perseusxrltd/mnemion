import { serveCredentialRequests } from '../dist/credential-process.js'

const mode = process.argv[2]
if (mode === 'malformed' || mode === 'oversized' || mode === 'exit' || mode === 'wrong-id') {
  process.stdin.once('data', () => {
    if (mode === 'exit') process.exit(2)
    process.stdout.write(mode === 'oversized' ? 'x'.repeat(32769) :
      mode === 'wrong-id' ? '{"type":"result","id":999,"ok":true,"value":true}\n' : 'not-json\n')
  })
} else {
  serveCredentialRequests({
    available: async () => {
      if (mode === 'hang') return new Promise(() => {})
      if (mode === 'denied') return false
      return true
    },
    encrypt: async value => {
      if (mode === 'error') throw new Error(value)
      if (mode === 'slow') await new Promise(resolve => setTimeout(resolve, 100))
      return Buffer.from('synthetic-fixture:' + value)
    },
    decrypt: async bytes => bytes.toString().slice('synthetic-fixture:'.length),
  }, process.stdin, process.stdout, () => process.memoryUsage().rss, () => process.exit(3))
}
