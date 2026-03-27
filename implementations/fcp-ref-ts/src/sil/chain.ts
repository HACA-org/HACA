// Append-only integrity chain — state/integrity_chain.jsonl.
// Each entry is linked to the previous via prev_hash = sha256Digest(JSON.stringify(prevEntry)).
// Genesis is written by FAP; this module appends post-genesis entries.
import { appendJsonl, fileExists } from '../store/io.js'
import { readJsonl } from '../store/io.js'
import { sha256Digest } from '../boot/integrity.js'
import type { Layout } from '../types/store.js'
import type { IntegrityChainEntry } from '../types/formats/integrity.js'

export async function readChain(layout: Layout): Promise<IntegrityChainEntry[]> {
  if (!await fileExists(layout.state.integrityChain)) return []
  const lines = await readJsonl(layout.state.integrityChain)
  return lines as IntegrityChainEntry[]
}

async function lastEntry(layout: Layout): Promise<IntegrityChainEntry | null> {
  const chain = await readChain(layout)
  return chain[chain.length - 1] ?? null
}

async function nextBase(layout: Layout): Promise<{ seq: number; ts: string; prev_hash: string }> {
  const prev = await lastEntry(layout)
  if (!prev) throw new Error('chain is empty — cannot append before genesis')
  return {
    seq:       prev.seq + 1,
    ts:        new Date().toISOString(),
    prev_hash: sha256Digest(JSON.stringify(prev)),
  }
}

export async function appendEndureCommit(
  layout: Layout,
  opts: {
    evolution_auth_digest: string
    files:                 Record<string, string>
    integrity_doc_hash:    string
  },
): Promise<void> {
  const base = await nextBase(layout)
  const entry: IntegrityChainEntry = {
    ...base,
    type:                  'ENDURE_COMMIT',
    evolution_auth_digest: opts.evolution_auth_digest as `sha256:${string}`,
    files:                 opts.files as Record<string, `sha256:${string}`>,
    integrity_doc_hash:    opts.integrity_doc_hash as `sha256:${string}`,
  }
  await appendJsonl(layout.state.integrityChain, entry)
}

export async function appendSeveranceCommit(
  layout: Layout,
  opts: {
    skill_removed: string
    reason:        string
    files:         Record<string, string>
    integrity_doc_hash: string
  },
): Promise<void> {
  const base = await nextBase(layout)
  const entry: IntegrityChainEntry = {
    ...base,
    type:               'SEVERANCE_COMMIT',
    skill_removed:      opts.skill_removed,
    reason:             opts.reason,
    files:              opts.files as Record<string, `sha256:${string}`>,
    integrity_doc_hash: opts.integrity_doc_hash as `sha256:${string}`,
  }
  await appendJsonl(layout.state.integrityChain, entry)
}

export async function appendModelChange(
  layout: Layout,
  opts: {
    from:               string
    to:                 string
    files:              Record<string, string>
    integrity_doc_hash: string
  },
): Promise<void> {
  const base = await nextBase(layout)
  const entry: IntegrityChainEntry = {
    ...base,
    type:               'MODEL_CHANGE',
    from:               opts.from,
    to:                 opts.to,
    files:              opts.files as Record<string, `sha256:${string}`>,
    integrity_doc_hash: opts.integrity_doc_hash as `sha256:${string}`,
  }
  await appendJsonl(layout.state.integrityChain, entry)
}
