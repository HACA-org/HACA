// fcp_evolution_proposal — SIL tool: queue an evolution proposal for Operator review.
import { randomUUID } from 'node:crypto'
import { sha256Digest } from '../../boot/integrity.js'
import { writeJson, readJson, fileExists } from '../../store/io.js'
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

interface Proposal {
  id:       string
  content:  string
  digest:   string
  queuedAt: string
}

interface ProposalsFile {
  proposals: Proposal[]
}

export const evolutionProposalHandler: ToolHandler = {
  name: 'fcp_evolution_proposal',
  async execute(params: unknown, ctx: ExecContext): Promise<ToolResult> {
    if (typeof params !== 'object' || params === null || typeof (params as Record<string, unknown>)['content'] !== 'string') {
      return { ok: false, error: 'content is required' }
    }
    const content = ((params as Record<string, unknown>)['content'] as string).trim()
    if (!content) return { ok: false, error: 'content must not be empty' }

    const proposal: Proposal = {
      id:       randomUUID(),
      content,
      digest:   sha256Digest(content),
      queuedAt: new Date().toISOString(),
    }

    const existing: ProposalsFile = await fileExists(ctx.layout.state.pendingProposals)
      ? (await readJson(ctx.layout.state.pendingProposals) as ProposalsFile)
      : { proposals: [] }

    await writeJson(ctx.layout.state.pendingProposals, {
      proposals: [...(existing.proposals ?? []), proposal],
    })

    ctx.logger.info('sil:evolution_proposal', { id: proposal.id })
    return { ok: true, output: `Evolution proposal queued. id: ${proposal.id}` }
  },
}
