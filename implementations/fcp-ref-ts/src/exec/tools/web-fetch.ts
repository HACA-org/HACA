// fcp_web_fetch — fetch a URL and return text content.
// Gate: asks if domain not in allowlist (once/session/add-to-allowlist/deny).
// Private/loopback addresses are always blocked — hard error, no gate.
import { resolveToolApproval } from '../../session/approval.js'
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

const MAX_BYTES  = 512 * 1024  // 512 KB
const TIMEOUT_MS = 15_000

const BLOCKED_PATTERNS = [
  /^https?:\/\/localhost/i,
  /^https?:\/\/127\./,
  /^https?:\/\/0\./,
  /^https?:\/\/\[::1\]/,
  /^https?:\/\/10\./,
  /^https?:\/\/192\.168\./,
  /^https?:\/\/172\.(1[6-9]|2\d|3[01])\./,
]

function extractUrl(params: unknown): string | null {
  if (typeof params === 'object' && params !== null && 'url' in params) {
    const u = (params as Record<string, unknown>)['url']
    return typeof u === 'string' ? u.trim() : null
  }
  return null
}

function isBlocked(url: string): boolean {
  return BLOCKED_PATTERNS.some(p => p.test(url))
}

export const webFetchHandler: ToolHandler = {
  name: 'fcp_web_fetch',
  async execute(params: unknown, ctx: ExecContext): Promise<ToolResult> {
    const url = extractUrl(params)
    if (!url) return { ok: false, error: 'url is required' }
    if (!/^https?:\/\//i.test(url)) return { ok: false, error: 'only http/https URLs are allowed' }
    if (isBlocked(url)) return { ok: false, error: 'private/loopback addresses are blocked' }

    // Extract hostname for allowlist check
    let hostname: string
    try {
      hostname = new URL(url).hostname
    } catch {
      return { ok: false, error: 'malformed URL' }
    }

    // Gate: domain not in allowlist
    if (!ctx.policy.domains.includes(hostname)) {
      const decision = await resolveToolApproval(
        `Fetch domain not in allowlist: ${hostname}`,
        'once-session-allowlist-deny',
        ctx.io,
      )
      if (!decision.granted) return { ok: false, error: 'Denied by operator.' }
      if (decision.tier === 'session')    await ctx.policy.addDomain(hostname, 'session')
      if (decision.tier === 'persistent') await ctx.policy.addDomain(hostname, 'persistent')
      // tier === 'one-time': fetch once without adding to policy
    }

    try {
      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
      let res: Response
      try {
        res = await fetch(url, {
          signal:  controller.signal,
          headers: { 'User-Agent': 'fcp-agent/1.0' },
        })
      } finally {
        clearTimeout(timer)
      }

      if (!res.ok) {
        return { ok: false, error: `HTTP ${res.status}: ${res.statusText}` }
      }

      const buf = await res.arrayBuffer()
      if (buf.byteLength > MAX_BYTES) {
        return { ok: false, error: `response too large (${buf.byteLength} bytes, max ${MAX_BYTES})` }
      }

      const text = new TextDecoder('utf-8', { fatal: false }).decode(buf)
      ctx.logger.info('exec:web_fetch', { url, bytes: buf.byteLength })
      return { ok: true, output: text }
    } catch (e: unknown) {
      return { ok: false, error: String(e) }
    }
  },
}
