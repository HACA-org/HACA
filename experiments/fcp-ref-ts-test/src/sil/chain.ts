import { existsSync } from 'node:fs'
import { join } from 'node:path'
import type { Layout } from '../store/layout.js'
import { appendJsonl, readJsonl } from '../store/io.js'
import { sha256Str } from './integrity.js'
import type { ChainEntry, ChainEntryType } from './types.js'

async function lastEntry(layout: Layout): Promise<ChainEntry | null> {
  if (!existsSync(layout.integrityChain)) return null
  const entries = await readJsonl<ChainEntry>(layout.integrityChain)
  return entries[entries.length - 1] ?? null
}

async function appendEntry(
  layout: Layout,
  type: ChainEntryType,
  data: Record<string, unknown>,
): Promise<ChainEntry> {
  const prev = await lastEntry(layout)
  const prevHash = prev ? sha256Str(JSON.stringify(prev)) : null
  const entry: ChainEntry = {
    seq: (prev?.seq ?? 0) + 1,
    type,
    ts: new Date().toISOString(),
    prevHash,
    data,
  }
  await appendJsonl(layout.integrityChain, entry)
  return entry
}

export async function logGenesis(layout: Layout, imprintHash: string): Promise<ChainEntry> {
  return appendEntry(layout, 'GENESIS', { imprintHash })
}

export async function logHeartbeat(layout: Layout, sessionId: string): Promise<ChainEntry> {
  return appendEntry(layout, 'HEARTBEAT', { sessionId })
}

export async function logCritical(
  layout: Layout,
  type: string,
  detail: Record<string, unknown>,
): Promise<ChainEntry> {
  return appendEntry(layout, 'CRITICAL', { type, ...detail })
}

export async function logSeveranceCommit(
  layout: Layout,
  skillName: string,
  issues: string[],
): Promise<ChainEntry> {
  return appendEntry(layout, 'SEVERANCE_COMMIT', { skill: skillName, issues })
}

export async function logEndureCommit(
  layout: Layout,
  operation: string,
  proposalId: string,
  evolutionAuthDigest: string,
): Promise<ChainEntry> {
  return appendEntry(layout, 'ENDURE_COMMIT', {
    operation,
    proposalId,
    evolutionAuthDigest,
  })
}

export async function logCriticalCleared(
  layout: Layout,
  clearsSeq: number,
): Promise<ChainEntry> {
  return appendEntry(layout, 'CRITICAL_CLEARED', { clearsSeq })
}

export async function logSleepComplete(
  layout: Layout,
  sessionId: string,
): Promise<ChainEntry> {
  return appendEntry(layout, 'SLEEP_COMPLETE', { sessionId })
}

export async function lastChainSeq(layout: Layout): Promise<number> {
  const entry = await lastEntry(layout)
  return entry?.seq ?? 0
}

export async function readChain(layout: Layout): Promise<ChainEntry[]> {
  if (!existsSync(layout.integrityChain)) return []
  return readJsonl<ChainEntry>(layout.integrityChain)
}
