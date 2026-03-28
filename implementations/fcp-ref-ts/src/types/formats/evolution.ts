import { z } from 'zod'

// ─── Evolution Op types ───────────────────────────────────────────────────────
// Each op represents one atomic structural change the SIL will execute during
// the Endure Protocol. Discriminated union keyed on `type`.

export const FileWriteOpSchema = z.object({
  type:    z.literal('fileWrite'),
  path:    z.string().min(1),   // relative to entity root
  content: z.string(),
})

export const FileDeleteOpSchema = z.object({
  type: z.literal('fileDelete'),
  path: z.string().min(1),
})

export const JsonMergeOpSchema = z.object({
  type:  z.literal('jsonMerge'),
  path:  z.string().min(1),
  patch: z.record(z.unknown()),   // shallow merge applied with Object.assign
})

export const SkillInstallOpSchema = z.object({
  type:    z.literal('skillInstall'),
  name:    z.string().min(1),
  version: z.string().min(1),
  source:  z.string().min(1),   // URI / path / npm specifier
})

export const EvolutionOpSchema = z.discriminatedUnion('type', [
  FileWriteOpSchema,
  FileDeleteOpSchema,
  JsonMergeOpSchema,
  SkillInstallOpSchema,
])

// ─── Proposal payload (what CPE passes to fcp_evolution_proposal) ─────────────
export const EvolutionProposalPayloadSchema = z.object({
  description: z.string().min(1),   // human-readable narrative for the Operator
  ops:         z.array(EvolutionOpSchema).min(1),
})

export type FileWriteOp              = z.infer<typeof FileWriteOpSchema>
export type FileDeleteOp             = z.infer<typeof FileDeleteOpSchema>
export type JsonMergeOp              = z.infer<typeof JsonMergeOpSchema>
export type SkillInstallOp           = z.infer<typeof SkillInstallOpSchema>
export type EvolutionOp              = z.infer<typeof EvolutionOpSchema>
export type EvolutionProposalPayload = z.infer<typeof EvolutionProposalPayloadSchema>
