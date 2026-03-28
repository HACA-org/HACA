// fcp_evolution_proposal — SIL tool: queue or auto-approve an evolution proposal.
//
// Structured payload: { description, ops[] }
// digest = sha256(JSON.stringify(ops))
//
// HACA-Core   (no authorizationScope): queue proposal → PROPOSAL_PENDING in integrity.log.
//             Operator must approve at session close before Endure runs.
//
// HACA-Evolve (authorizationScope present): auto-approve if all ops fall within the
//             granted scope flags. Ops outside scope fall back to HACA-Core queueing.
//             EVOLUTION_AUTH written immediately for auto-approved proposals.
import { randomUUID } from 'node:crypto'
import { sha256Digest } from '../../boot/integrity.js'
import { ensureDir, writeJson, readJson, fileExists } from '../../store/io.js'
import { appendIntegrityLog } from '../integrity.js'
import { EvolutionProposalPayloadSchema } from '../../types/formats/evolution.js'
import type { EvolutionOp } from '../../types/formats/evolution.js'
import type { AuthorizationScope } from '../../types/formats/baseline.js'
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'
import type { EndureProposal } from '../../types/sil.js'

// ─── scope classification ─────────────────────────────────────────────────────

function opsRequiredScope(ops: EvolutionOp[]): {
  needsEvolution: boolean
  needsSkills:    boolean
} {
  let needsEvolution = false
  let needsSkills    = false
  for (const op of ops) {
    if (op.type === 'skillInstall') needsSkills    = true
    else                           needsEvolution = true
  }
  return { needsEvolution, needsSkills }
}

function scopeCoversOps(scope: AuthorizationScope, ops: EvolutionOp[]): boolean {
  const { needsEvolution, needsSkills } = opsRequiredScope(ops)
  if (needsEvolution && !scope.autonomousEvolution) return false
  if (needsSkills    && !scope.autonomousSkills)    return false
  if (scope.renewalDays > 0) {
    const grantedMs  = new Date(scope.grantedAt).getTime()
    const expiresMs  = grantedMs + scope.renewalDays * 86_400_000
    if (Date.now() > expiresMs) return false
  }
  return true
}

// ─── proposals file helpers ───────────────────────────────────────────────────

async function loadProposals(filePath: string): Promise<EndureProposal[]> {
  try {
    const raw = await readJson(filePath) as { proposals?: unknown }
    if (!Array.isArray(raw?.proposals)) return []
    return raw.proposals as EndureProposal[]
  } catch {
    return []
  }
}

// ─── handler ─────────────────────────────────────────────────────────────────

export const evolutionProposalHandler: ToolHandler = {
  name: 'fcp_evolution_proposal',
  description: 'Propose a structural evolution to the entity. Each proposal contains a human-readable description and a list of ops (fileWrite, fileDelete, jsonMerge, skillInstall). HACA-Core: queued for Operator approval at session close. HACA-Evolve: auto-approved if within authorization_scope.',
  inputSchema: {
    type: 'object',
    properties: {
      description: { type: 'string', description: 'Human-readable explanation of the proposed change (shown to Operator for approval).' },
      ops: {
        type: 'array',
        description: 'List of structural operations to execute atomically during the Endure Protocol.',
        items: {
          oneOf: [
            { type: 'object', properties: { type: { type: 'string', enum: ['fileWrite'] }, path: { type: 'string' }, content: { type: 'string' } }, required: ['type', 'path', 'content'] },
            { type: 'object', properties: { type: { type: 'string', enum: ['fileDelete'] }, path: { type: 'string' } }, required: ['type', 'path'] },
            { type: 'object', properties: { type: { type: 'string', enum: ['jsonMerge'] }, path: { type: 'string' }, patch: { type: 'object' } }, required: ['type', 'path', 'patch'] },
            { type: 'object', properties: { type: { type: 'string', enum: ['skillInstall'] }, name: { type: 'string' }, version: { type: 'string' }, source: { type: 'string' } }, required: ['type', 'name', 'version', 'source'] },
          ],
        },
        minItems: 1,
      },
    },
    required: ['description', 'ops'],
  },
  async execute(params: unknown, ctx: ExecContext): Promise<ToolResult> {
    const parsed = EvolutionProposalPayloadSchema.safeParse(params)
    if (!parsed.success) {
      return { ok: false, error: `Invalid payload: ${parsed.error.issues.map(i => i.message).join('; ')}` }
    }
    const { description, ops } = parsed.data
    const digest    = sha256Digest(JSON.stringify(ops))
    const id        = randomUUID()
    const queuedAt  = new Date().toISOString()
    const scope     = ctx.baseline.authorizationScope

    // Determine approval status
    const autoApproved = scope !== undefined && scopeCoversOps(scope, ops)

    const proposal: EndureProposal = {
      id,
      description,
      ops,
      digest,
      queuedAt,
      ...(autoApproved ? { approvedAt: queuedAt } : {}),
    }

    await ensureDir(ctx.layout.state.dir)

    const existing = await fileExists(ctx.layout.state.pendingProposals)
      ? await loadProposals(ctx.layout.state.pendingProposals)
      : []

    await writeJson(ctx.layout.state.pendingProposals, {
      proposals: [...existing, proposal],
    })

    const ts = new Date().toISOString()
    if (autoApproved) {
      await appendIntegrityLog(ctx.layout, { event: 'EVOLUTION_AUTH', id, digest, ts, autoApproved: true })
      ctx.logger.info('sil:evolution_proposal:auto_approved', { id })
      return { ok: true, output: `Evolution proposal auto-approved (HACA-Evolve scope). id: ${id}` }
    } else {
      await appendIntegrityLog(ctx.layout, { event: 'PROPOSAL_PENDING', id, digest, ts })
      ctx.logger.info('sil:evolution_proposal:queued', { id })
      return { ok: true, output: `Evolution proposal queued for Operator approval. id: ${id}` }
    }
  },
}
