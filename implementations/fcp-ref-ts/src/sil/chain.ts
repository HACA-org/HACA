// Append-only integrity chain — state/integrity-chain.jsonl.
// Each entry is linked to the previous via prevHash = sha256Digest(JSON.stringify(prevEntry)).
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

async function nextBase(layout: Layout): Promise<{ seq: number; ts: string; prevHash: string }> {
  const prev = await lastEntry(layout)
  if (!prev) throw new Error('chain is empty — cannot append before genesis')
  return {
    seq:      prev.seq + 1,
    ts:       new Date().toISOString(),
    prevHash: sha256Digest(JSON.stringify(prev)),
  }
}

export async function appendEndureCommit(
  layout: Layout,
  opts: {
    evolutionAuthDigest: string
    files:               Record<string, string>
    integrityDocHash:    string
  },
): Promise<void> {
  const base = await nextBase(layout)
  const entry: IntegrityChainEntry = {
    ...base,
    type:                'ENDURE_COMMIT',
    evolutionAuthDigest: opts.evolutionAuthDigest as `sha256:${string}`,
    files:               opts.files as Record<string, `sha256:${string}`>,
    integrityDocHash:    opts.integrityDocHash as `sha256:${string}`,
  }
  await appendJsonl(layout.state.integrityChain, entry)
}

export async function appendSeveranceCommit(
  layout: Layout,
  opts: {
    skillRemoved:     string
    reason:           string
    files:            Record<string, string>
    integrityDocHash: string
  },
): Promise<void> {
  const base = await nextBase(layout)
  const entry: IntegrityChainEntry = {
    ...base,
    type:             'SEVERANCE_COMMIT',
    skillRemoved:     opts.skillRemoved,
    reason:           opts.reason,
    files:            opts.files as Record<string, `sha256:${string}`>,
    integrityDocHash: opts.integrityDocHash as `sha256:${string}`,
  }
  await appendJsonl(layout.state.integrityChain, entry)
}

export async function appendModelChange(
  layout: Layout,
  opts: {
    from:             string
    to:               string
    files:            Record<string, string>
    integrityDocHash: string
  },
): Promise<void> {
  const base = await nextBase(layout)
  const entry: IntegrityChainEntry = {
    ...base,
    type:             'MODEL_CHANGE',
    from:             opts.from,
    to:               opts.to,
    files:            opts.files as Record<string, `sha256:${string}`>,
    integrityDocHash: opts.integrityDocHash as `sha256:${string}`,
  }
  await appendJsonl(layout.state.integrityChain, entry)
}
