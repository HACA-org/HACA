// SHA-256 utilities and tracked-file enumeration.
// Used by FAP (step 5) and Phase 3 (verification at every boot).

import { createHash } from 'node:crypto'
import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { fileExists } from '../store/io.js'
import type { Layout } from '../types/store.js'

// Raw hex digest — used for integrity.json `files` values.
export function sha256Hex(data: string | Buffer): string {
  return createHash('sha256').update(data).digest('hex')
}

// `sha256:` prefixed digest — used for chain entries and imprint hashes.
export function sha256Digest(data: string | Buffer): string {
  return 'sha256:' + sha256Hex(data)
}

// Hash a file as it currently exists on disk (raw hex, no prefix).
export async function sha256File(filePath: string): Promise<string> {
  const buf = await fs.readFile(filePath)
  return sha256Hex(buf)
}

// Enumerate all tracked structural files relative to entity root.
// Spec §3.3: boot.md, all persona/ files, skills/index.json,
// all skill manifest.json files, all hooks/ files, state/baseline.json.
export async function getTrackedFiles(layout: Layout): Promise<string[]> {
  const tracked: string[] = ['boot.md', 'state/baseline.json']

  // persona/ — all direct files
  for (const entry of await safeReaddir(layout.persona)) {
    if (!entry.isDirectory()) tracked.push(`persona/${entry.name}`)
  }

  // hooks/ — recursive
  await collectRecursive(layout.hooks, 'hooks', tracked)

  // skills/index.json — always included if present
  if (await fileExists(layout.skills.index)) {
    tracked.push('skills/index.json')
  }

  // skills/<name>/manifest.json — custom skills
  for (const entry of await safeReaddir(layout.skills.dir)) {
    if (!entry.isDirectory() || entry.name === 'lib') continue
    const manifest = path.join(layout.skills.dir, entry.name, 'manifest.json')
    if (await fileExists(manifest)) {
      tracked.push(`skills/${entry.name}/manifest.json`)
    }
  }

  // skills/lib/<name>/manifest.json — built-in skills
  for (const entry of await safeReaddir(layout.skills.lib)) {
    if (!entry.isDirectory()) continue
    const manifest = path.join(layout.skills.lib, entry.name, 'manifest.json')
    if (await fileExists(manifest)) {
      tracked.push(`skills/lib/${entry.name}/manifest.json`)
    }
  }

  return tracked
}

// Compute hashes of all tracked files. Returns a record suitable for
// IntegrityDocument.files. Throws if a tracked file is missing.
export async function hashTrackedFiles(
  layout: Layout,
  tracked: string[],
): Promise<Record<string, string>> {
  const files: Record<string, string> = {}
  for (const rel of tracked) {
    const abs = path.join(layout.root, rel)
    files[rel] = await sha256File(abs)
  }
  return files
}

// --- helpers ---

async function safeReaddir(dirPath: string): Promise<import('node:fs').Dirent[]> {
  try {
    return await fs.readdir(dirPath, { withFileTypes: true })
  } catch {
    return []
  }
}

async function collectRecursive(
  dirPath: string,
  relPrefix: string,
  out: string[],
): Promise<void> {
  for (const entry of await safeReaddir(dirPath)) {
    const rel = `${relPrefix}/${entry.name}`
    if (entry.isDirectory()) {
      await collectRecursive(path.join(dirPath, entry.name), rel, out)
    } else {
      out.push(rel)
    }
  }
}
