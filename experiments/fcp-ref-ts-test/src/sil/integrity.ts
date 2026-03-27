import { createHash } from 'node:crypto'
import { existsSync } from 'node:fs'
import { readFile, readdir } from 'node:fs/promises'
import { join } from 'node:path'
import type { Layout } from '../store/layout.js'
import { readJson, writeJson } from '../store/io.js'
import type { ImprintRecord } from '../boot/types.js'

export interface IntegrityDocument {
  version: '1.0'
  algorithm: 'sha256'
  files: Record<string, string>  // relative path → sha256 hash
}

export function sha256File(content: string): string {
  return 'sha256:' + createHash('sha256').update(content, 'utf8').digest('hex')
}

export function sha256Str(s: string): string {
  return 'sha256:' + createHash('sha256').update(s, 'utf8').digest('hex')
}

/**
 * Returns all files that must be tracked in the integrity document.
 * Covers: BOOT.md, baseline.json, skills/index.json, persona/*.md, skills/*\/manifest.json
 */
export async function trackedFiles(layout: Layout): Promise<string[]> {
  const paths: string[] = []

  if (existsSync(layout.bootMd)) paths.push(layout.bootMd)
  if (existsSync(layout.baseline)) paths.push(layout.baseline)
  if (existsSync(layout.skillsIndex)) paths.push(layout.skillsIndex)

  // persona/ files
  if (existsSync(layout.persona)) {
    const files = (await readdir(layout.persona))
      .filter(f => f.endsWith('.md'))
      .sort()
      .map(f => join(layout.persona, f))
    paths.push(...files)
  }

  // skills/*/manifest.json
  if (existsSync(layout.skills)) {
    const skillDirs = await readdir(layout.skills)
    for (const dir of skillDirs.sort()) {
      const manifestPath = join(layout.skills, dir, 'manifest.json')
      if (existsSync(manifestPath)) paths.push(manifestPath)
    }
  }

  return paths
}

/**
 * Compute SHA-256 hashes for all tracked files.
 * Returns a map of relative path → hash.
 */
export async function computeHashes(layout: Layout): Promise<Record<string, string>> {
  const files = await trackedFiles(layout)
  const result: Record<string, string> = {}
  for (const absPath of files) {
    const rel = absPath.startsWith(layout.root + '/')
      ? absPath.slice(layout.root.length + 1)
      : absPath
    const content = await readFile(absPath, 'utf8')
    result[rel] = sha256File(content)
  }
  return result
}

/**
 * Write state/integrity.json with current file hashes.
 */
export async function writeIntegrityDoc(layout: Layout): Promise<IntegrityDocument> {
  const files = await computeHashes(layout)
  const doc: IntegrityDocument = { version: '1.0', algorithm: 'sha256', files }
  await writeJson(layout.integrity, doc)
  return doc
}

/**
 * Verify current file hashes against integrity.json.
 * Returns list of drift descriptions (empty = clean).
 */
export async function verifyDrift(layout: Layout): Promise<string[]> {
  if (!existsSync(layout.integrity)) return ['integrity.json not found']

  const doc = await readJson<IntegrityDocument>(layout.integrity)
  const drifts: string[] = []

  for (const [rel, expected] of Object.entries(doc.files)) {
    const absPath = join(layout.root, rel)
    if (!existsSync(absPath)) {
      drifts.push(`missing: ${rel}`)
      continue
    }
    const content = await readFile(absPath, 'utf8')
    const actual = sha256File(content)
    if (actual !== expected) {
      drifts.push(`hash mismatch: ${rel}`)
    }
  }

  return drifts
}

export interface ChainVerificationResult {
  valid: boolean
  reason?: string
}

/**
 * Verify the integrity chain from GENESIS to last entry.
 *
 * Rules:
 * 1. First entry must be GENESIS with imprintHash matching genesisOmega in imprint.json
 * 2. Each subsequent entry's prevHash must equal sha256Str(JSON.stringify(previousEntry))
 * 3. Every ENDURE_COMMIT must have a non-empty evolutionAuthDigest
 *
 * An empty chain (entity has never evolved) is valid as long as imprint exists.
 */
export async function verifyChainFromImprint(layout: Layout): Promise<ChainVerificationResult> {
  if (!existsSync(layout.imprint)) {
    return { valid: false, reason: 'imprint.json not found' }
  }

  const imprint = await readJson<ImprintRecord>(layout.imprint)
  if (!imprint.genesisOmega) {
    return { valid: false, reason: 'imprint.json missing genesisOmega' }
  }

  // No chain yet — entity has not evolved, valid by definition
  if (!existsSync(layout.integrityChain)) {
    return { valid: true }
  }

  const { readJsonl } = await import('../store/io.js')
  const entries = await readJsonl<Record<string, unknown>>(layout.integrityChain)

  if (entries.length === 0) return { valid: true }

  // Rule 1: first entry must be GENESIS with correct imprintHash
  const first = entries[0]!
  if (first['type'] !== 'GENESIS') {
    return { valid: false, reason: `first chain entry is not GENESIS (got ${first['type']})` }
  }
  if (first['data'] == null || (first['data'] as Record<string, unknown>)['imprintHash'] !== imprint.genesisOmega) {
    return { valid: false, reason: 'GENESIS imprintHash does not match genesisOmega' }
  }

  // Rules 2 & 3: traverse remaining entries
  let prevEntry = first
  for (let i = 1; i < entries.length; i++) {
    const entry = entries[i]!
    const expectedPrevHash = sha256Str(JSON.stringify(prevEntry))

    // Rule 2: prevHash linkage
    if (entry['prevHash'] !== expectedPrevHash) {
      return {
        valid: false,
        reason: `chain broken at seq ${entry['seq']}: prevHash mismatch`,
      }
    }

    // Rule 3: ENDURE_COMMIT must have evolutionAuthDigest
    if (entry['type'] === 'ENDURE_COMMIT') {
      const data = entry['data'] as Record<string, unknown> | undefined
      if (!data?.['evolutionAuthDigest']) {
        return {
          valid: false,
          reason: `ENDURE_COMMIT at seq ${entry['seq']} missing evolutionAuthDigest`,
        }
      }
    }

    prevEntry = entry
  }

  return { valid: true }
}
