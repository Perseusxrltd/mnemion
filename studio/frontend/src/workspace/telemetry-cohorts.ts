/** Coarse v2 cohort arguments. One sampled view may use one of them; this is not fleet data. */
import { version } from '../../package.json'

const platforms = ['windows', 'macos', 'linux', 'other'] as const
const architectures = ['x64', 'arm64', 'other'] as const

function family(value: string): 'before_4' | '4' | '5_plus' | 'unobserved' {
  const major = Number(value.split('.')[0])
  if (!Number.isInteger(major) || major < 0) return 'unobserved'
  if (major < 4) return 'before_4'
  if (major === 4) return '4'
  return '5_plus'
}

function knownPlatform(value: string | undefined): (typeof platforms)[number] | null {
  if (!value) return null
  const name = value.toLowerCase()
  if (name.includes('android')) return 'other'
  if (name.includes('win')) return 'windows'
  if (name.includes('mac')) return 'macos'
  if (name.includes('linux')) return 'linux'
  return 'other'
}

function knownArchitecture(value: string | undefined): (typeof architectures)[number] | null {
  if (value === 'x64') return 'x64'
  if (value === 'arm' || value === 'arm64') return 'arm64'
  return null
}

export function reviewedBrowserRelease(): [number, number, number] | null {
  const parts = version.split('.')
  if (parts.length !== 3 || parts.some(part => !/^\d{1,3}$/.test(part))) return null
  const numbers = parts.map(Number)
  if (numbers.some(part => !Number.isInteger(part) || part > 255)) return null
  return numbers as [number, number, number]
}

export function reviewedBrowserOperatingSystem(): (typeof platforms)[number] | null {
  const platform = knownPlatform(
    (typeof navigator === 'undefined' ? undefined : (navigator as Navigator & { userAgentData?: { platform?: string } }).userAgentData?.platform)
      ?? (typeof navigator === 'undefined' ? undefined : navigator.platform),
  )
  return platform
}

export function reviewedBrowserCohorts(): { platform?: string; architecture?: string; release_family: string } {
  const nav = typeof navigator === 'undefined' ? undefined : navigator
  const hinted = (nav as Navigator & { userAgentData?: { platform?: string; architecture?: string } } | undefined)?.userAgentData
  const cohorts: { platform?: string; architecture?: string; release_family: string } = {
    release_family: family(version),
  }
  const platform = knownPlatform(hinted?.platform ?? nav?.platform)
  const architecture = knownArchitecture(hinted?.architecture)
  if (platform) cohorts.platform = platform
  if (architecture) cohorts.architecture = architecture
  return cohorts
}
