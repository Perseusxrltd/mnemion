/** Coarse v2 cohort arguments for the desktop owner. Not a hardware fingerprint or a v3 report. */
import { version } from './package.json'

function family(value: string): 'before_4' | '4' | '5_plus' | 'unobserved' {
  const major = Number(value.split('.')[0])
  if (!Number.isInteger(major) || major < 0) return 'unobserved'
  return major < 4 ? 'before_4' : major === 4 ? '4' : '5_plus'
}

export function reviewedDesktopCohorts(): { platform: string; architecture: string; release_family: string } {
  const platform = process.platform === 'win32' ? 'windows'
    : process.platform === 'darwin' ? 'macos'
      : process.platform === 'linux' ? 'linux'
        : 'other'
  const architecture = process.arch === 'x64' ? 'x64' : process.arch === 'arm64' ? 'arm64' : 'other'
  return { platform, architecture, release_family: family(version) }
}
