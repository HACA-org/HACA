// fcp_evolution_proposal — SIL tool: queue an evolution proposal for Operator review.
import { randomUUID } from 'node:crypto'
import { z } from 'zod'
import { sha256Digest } from '../../boot/integrity.js'
import { ensureDir, writeJson, readJson, fileExists } from '../../store/io.js'
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

const ProposalSchema = z.object({
  id:         z.string(),
  content:    z.string(),
  digest:     z.string(),
  queuedAt:   z.string(),
  approvedAt: z.string().optional(),
})

const ProposalsFileSchema = z.object({
  proposals: z.array(ProposalSchema),
})

type Proposal = z.infer<typeof ProposalSchema>

async function loadProposals(filePath: string): Promise<Proposal[]> {
  try {
    const raw = await readJson(filePath)
    return ProposalsFileSchema.parse(raw).proposals
  } catch {
    return []
  }
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

    await ensureDir(ctx.layout.state.dir)

    const existing = await fileExists(ctx.layout.state.pendingProposals)
      ? await loadProposals(ctx.layout.state.pendingProposals)
      : []

    await writeJson(ctx.layout.state.pendingProposals, {
      proposals: [...existing, proposal],
    })

    ctx.logger.info('sil:evolution_proposal', { id: proposal.id })
    return { ok: true, output: `Evolution proposal queued. id: ${proposal.id}` }
  },
}
