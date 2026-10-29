/** Verify actual executable entitlements, in addition to intact bundle seals. */
import { spawnSync } from 'node:child_process'
import { join } from 'node:path'

const required = ['com.apple.security.cs.allow-jit', 'com.apple.security.cs.disable-library-validation']

export function validateAdhocLaunchPolicy(description, entitlements) {
  if (typeof description !== 'string' || description.length > 65536 ||
      !/^Signature=adhoc$/m.test(description) || !/^TeamIdentifier=not set$/m.test(description) ||
      !/^CodeDirectory[^\n]*flags=[^\n]*\bruntime\b/m.test(description)) {
    throw new Error('The free Mac build requires an ad-hoc signature with hardened runtime enabled')
  }
  if (!entitlements || typeof entitlements !== 'object' || Array.isArray(entitlements) ||
      Object.keys(entitlements).sort().join(',') !== required.join(',') ||
      required.some(key => entitlements[key] !== true)) {
    throw new Error('The ad-hoc Mac build requires reviewed JIT and library-validation entitlements')
  }
  return { ad_hoc: true, hardened_runtime: true, jit: true, library_validation_exception: true }
}

function command(program, args, input) {
  const result = spawnSync(program, args, { encoding: 'utf8', input, timeout: 30000, maxBuffer: 65536 })
  if (result.error || result.status !== 0) throw new Error('Cannot inspect the actual Mac executable signing policy')
  return result
}

export function verifyAdhocMacLaunchPolicy(bundle) {
  if (process.platform !== 'darwin') throw new Error('Mac signing inspection requires native macOS')
  const targets = [bundle, ...['', ' (GPU)', ' (Renderer)', ' (Plugin)'].map(suffix =>
    join(bundle, 'Contents', 'Frameworks', 'Mnemion Studio Helper' + suffix + '.app'))]
  for (const target of targets) {
    const description = command('codesign', ['--display', '--verbose=4', target]).stderr
    const xml = command('codesign', ['--display', '--entitlements', ':-', target]).stdout
    const entitlements = JSON.parse(command('/usr/bin/plutil', ['-convert', 'json', '-o', '-', '--', '-'], xml).stdout)
    validateAdhocLaunchPolicy(description, entitlements)
  }
  return { executables_checked: targets.length, ad_hoc: true, hardened_runtime: true,
    jit: true, library_validation_exception: true }
}
