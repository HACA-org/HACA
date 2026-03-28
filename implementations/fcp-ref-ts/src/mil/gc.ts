// MIL GC — garbage collection stage of the Sleep Cycle.
// Compacts memory/session.jsonl: keeps N most recent conversation turns,
// truncates tool_result/tool_use content to short previews.
// Called by the sleep cycle orchestrator; only runs when compact was triggered.
// Target: reduce session history to ~22% of model context window.
import * as fs from 'node:fs/promises'
import { fileExists } from '../store/io.js'
import type { Layout } from '../types/store.js'
import type { Logger } from '../types/logger.js'

// Characters to keep from tool_result and tool_use content after truncation.
const TOOL_CONTENT_PREVIEW = 120

// Fraction of window to target after GC (used to derive message keep count).
const TARGET_WINDOW_FRACTION = 0.22

// Minimum messages to keep regardless of calculation (avoid empty history).
const MIN_KEEP = 4

export interface GCResult {
  readonly originalLines: number
  readonly keptLines:     number
}

export async function compactSessionHistory(
  layout:        Layout,
  contextWindow: number,
  logger:        Logger,
): Promise<GCResult> {
  if (!await fileExists(layout.memory.sessionJsonl)) {
    return { originalLines: 0, keptLines: 0 }
  }

  const raw = await fs.readFile(layout.memory.sessionJsonl, 'utf8')
  const lines = raw.split('\n').filter(l => l.trim() !== '')
  const originalLines = lines.length

  // Parse each line; skip unparseable ones
  const records: unknown[] = []
  for (const line of lines) {
    try { records.push(JSON.parse(line)) } catch { /* skip corrupt lines */ }
  }

  // Derive how many message lines to keep.
  // Rough heuristic: average message ≈ 500 chars ≈ 125 tokens.
  // Target window fraction at ~125 tokens/record.
  const targetTokens = contextWindow * TARGET_WINDOW_FRACTION
  const keepCount    = Math.max(MIN_KEEP, Math.floor(targetTokens / 125))

  // Separate session_open/session_close bookkeeping from conversation records
  const bookkeeping = records.filter(r => isBookkeeping(r))
  const conversation = records.filter(r => !isBookkeeping(r))

  const kept = conversation.slice(-keepCount).map(truncateRecord)
  const result = [...bookkeeping.slice(0, 1), ...kept]   // keep first bookkeeping entry (session_open)

  const out = result.map(r => JSON.stringify(r)).join('\n') + '\n'
  await fs.writeFile(layout.memory.sessionJsonl, out, 'utf8')

  logger.info('mil:gc', { originalLines, keptLines: result.length, keepCount })
  return { originalLines, keptLines: result.length }
}

function isBookkeeping(r: unknown): boolean {
  if (typeof r !== 'object' || r === null) return false
  const type = (r as Record<string, unknown>)['type']
  return type === 'session_open' || type === 'session_close'
}

function truncateRecord(r: unknown): unknown {
  if (typeof r !== 'object' || r === null) return r
  const rec = r as Record<string, unknown>

  if (rec['type'] === 'tool_execution') {
    // Keep tool name and timestamp, drop large input/output blobs
    return { type: rec['type'], tool: rec['tool'], approved: rec['approved'], ts: rec['ts'] }
  }

  if (rec['type'] === 'message') {
    const content = rec['content']
    if (Array.isArray(content)) {
      return {
        ...rec,
        content: content.map(block => truncateBlock(block)),
      }
    }
  }

  return r
}

function truncateBlock(block: unknown): unknown {
  if (typeof block !== 'object' || block === null) return block
  const b = block as Record<string, unknown>

  if (b['type'] === 'tool_result') {
    const text = typeof b['content'] === 'string' ? b['content'] : JSON.stringify(b['content'])
    const preview = text.length > TOOL_CONTENT_PREVIEW
      ? text.slice(0, TOOL_CONTENT_PREVIEW) + `…[${text.length - TOOL_CONTENT_PREVIEW} chars truncated]`
      : text
    return { type: b['type'], tool_use_id: b['tool_use_id'], content: preview }
  }

  if (b['type'] === 'tool_use') {
    const inputStr = JSON.stringify(b['input'] ?? {})
    const preview  = inputStr.length > TOOL_CONTENT_PREVIEW
      ? inputStr.slice(0, TOOL_CONTENT_PREVIEW) + '…'
      : inputStr
    return { type: b['type'], id: b['id'], name: b['name'], input: preview }
  }

  return block
}
