/** Coarse v2 cohort arguments for the desktop owner. Not a hardware fingerprint or a v3 report. */
import { readFileSync } from 'node:fs'

// The compiled file lives in dist/. Node 22 rejects a JSON import that has no
// type attribute, and this tsconfig does not emit one. Read the manifest beside dist.
const { version } = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8')) as { version: string }

function family(value: string): 'before_4' | '4' | '5_plus' | 'unobserved' {
  const major = Number(value.split('.')[0])
  if (!Number.isInteger(major) || major < 0) return 'unobserved'
  return major < 4 ? 'before_4' : major === 4 ? '4' : '5_plus'
}

const operatingSystems = ['windows', 'macos', 'linux', 'other'] as const

export function reviewedDesktopRelease(): [number, number, number] | null {
  const parts = version.split('.')
  if (parts.length !== 3 || parts.some(part => !/^\d{1,3}$/.test(part))) return null
  const numbers = parts.map(Number)
  if (numbers.some(part => !Number.isInteger(part) || part > 255)) return null
  return numbers as [number, number, number]
}

export function reviewedDesktopOperatingSystem(): (typeof operatingSystems)[number] {
  return process.platform === 'win32' ? 'windows'
    : process.platform === 'darwin' ? 'macos'
      : process.platform === 'linux' ? 'linux'
        : 'other'
}

export function cohortOperatingSystem(cohorts: unknown): (typeof operatingSystems)[number] | null {
  if (!cohorts || typeof cohorts !== 'object' || Array.isArray(cohorts)) return null
  const platform = (cohorts as { platform?: unknown }).platform
  return typeof platform === 'string' && operatingSystems.includes(platform as (typeof operatingSystems)[number])
    ? platform as (typeof operatingSystems)[number] : null
}

export function reviewedDesktopCohorts(): { platform: string; architecture: string; release_family: string } {
  const platform = process.platform === 'win32' ? 'windows'
    : process.platform === 'darwin' ? 'macos'
      : process.platform === 'linux' ? 'linux'
        : 'other'
  const architecture = process.arch === 'x64' ? 'x64' : process.arch === 'arm64' ? 'arm64' : 'other'
  return { platform, architecture, release_family: family(version) }
}
