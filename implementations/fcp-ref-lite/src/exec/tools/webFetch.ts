import type { Layout } from '../../store/layout.js'
import type { Logger } from '../../logger/logger.js'
import type { ToolHandler } from '../../session/loop.js'
import { readAllowlist, isDomainAllowed, addToAllowlist } from '../allowlist.js'

const TIMEOUT_MS = 15_000
const MAX_BYTES = 512 * 1024 // 512KB

export function createWebFetchTool(
  layout: Layout,
  logger: Logger,
  requestApproval: (prompt: string) => Promise<'once' | 'session' | 'allow' | 'deny'>,
): ToolHandler {
  return {
    definition: {
      name: 'webFetch',
      description: 'Fetch content from a URL. Operator must approve each domain (can be persisted).',
      input_schema: {
        type: 'object',
        properties: {
          url: { type: 'string', description: 'The URL to fetch' },
        },
        required: ['url'],
      },
    },
    async handle(input) {
      const url = String(input['url'] ?? '').trim()
      if (!url) return 'Error: url is required'

      let hostname: string
      try {
        hostname = new URL(url).hostname
      } catch {
        return 'Error: invalid URL'
      }

      const allowlist = await readAllowlist(layout)
      const domainAllowed = isDomainAllowed(allowlist, url)

      if (!domainAllowed) {
        const decision = await requestApproval(`webFetch: ${hostname}`)
        if (decision === 'deny') return 'Fetch denied by operator.'
        if (decision === 'allow') {
          await addToAllowlist(layout, 'webFetch', hostname)
        }
        // 'once' and 'session' proceed without persisting
      }

      try {
        await logger.info('exec', 'web_fetch', { url })
        const controller = new AbortController()
        const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
        const res = await fetch(url, { signal: controller.signal })
        clearTimeout(timer)

        if (!res.ok) return `Error: HTTP ${res.status} ${res.statusText}`

        const contentType = res.headers.get('content-type') ?? ''
        if (!contentType.includes('text') && !contentType.includes('json')) {
          return `Error: unsupported content-type: ${contentType}`
        }

        const buffer = await res.arrayBuffer()
        if (buffer.byteLength > MAX_BYTES) {
          return `Error: response too large (${buffer.byteLength} bytes, max ${MAX_BYTES})`
        }

        return new TextDecoder().decode(buffer)
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e)
        await logger.error('exec', 'web_fetch_error', { url, error: msg })
        return `Error: ${msg}`
      }
    },
  }
}
