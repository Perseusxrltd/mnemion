import assert from 'node:assert/strict'
import test from 'node:test'
import {
  HEAP_FIELDS,
  LINUX_FIELDS,
  parseLinuxStatus,
  readBoundedLinuxStatus,
  selectHeap,
} from './phase-memory.mjs'

const status = [
  'Name:   bash',
  'VmPeak:     131168 kB',
  'VmHWM:\t   13484 kB',
  'VmRSS:\t   13484 kB',
  'RssAnon:\t   10264 kB',
  'RssFile:\t    3220 kB',
  'RssShmem:\t       0 kB',
].join('\n')

test('keeps the five residency counters and drops the process name', () => {
  const parsed = parseLinuxStatus(status)
  assert.deepEqual(Object.keys(parsed), LINUX_FIELDS)
  assert.equal(parsed.VmRSS, 13484 * 1024)
  assert.equal(parsed.VmHWM, 13484 * 1024)
  assert.equal(parsed.RssAnon, 10264 * 1024)
  assert.equal(parsed.RssFile, 3220 * 1024)
  assert.equal(parsed.RssShmem, 0)
  assert.equal(JSON.stringify(parsed).includes('bash'), false)
  assert.equal(JSON.stringify(parsed).includes('VmPeak'), false)
})

test('a missing counter stays null', () => {
  const parsed = parseLinuxStatus('VmRSS:\t   10 kB\n')
  assert.equal(parsed.VmRSS, 10240)
  assert.equal(parsed.RssAnon, null)
  assert.equal(parsed.RssFile, null)
  assert.equal(parsed.RssShmem, null)
  assert.equal(parsed.VmHWM, null)
})

test('an oversized status is unavailable rather than partly parsed', () => {
  const parsed = parseLinuxStatus(`VmRSS:\t   10 kB\n${'x'.repeat(65536)}`)
  assert.deepEqual(Object.fromEntries(LINUX_FIELDS.map(field => [field, null])), parsed)
})

test('a non-linux read stays unavailable and retains no status text', () => {
  assert.notEqual(process.platform, 'linux')
  const parsed = readBoundedLinuxStatus()
  assert.deepEqual(Object.keys(parsed), LINUX_FIELDS)
  assert.deepEqual(Object.values(parsed), LINUX_FIELDS.map(() => null))
})

test('heap selection keeps committed, reserved and live bytes only', () => {
  const selected = selectHeap({
    total_heap_size: 7326976,
    total_physical_size: false,
    used_heap_size: 1.5,
    malloced_memory: 0,
    space_name: 'old_space',
    number_of_native_contexts: 1,
    external_memory: -4,
  })
  assert.deepEqual(Object.keys(selected), HEAP_FIELDS)
  assert.equal(selected.total_heap_size, 7326976)
  assert.equal(selected.total_physical_size, null)
  assert.equal(selected.used_heap_size, null)
  assert.equal(selected.malloced_memory, 0)
  assert.equal(selectHeap(null).total_heap_size, null)
  assert.equal(JSON.stringify(selected).includes('old_space'), false)
})
