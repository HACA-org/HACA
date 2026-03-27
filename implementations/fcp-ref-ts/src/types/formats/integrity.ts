import { z } from 'zod'

const sha256 = z.string().startsWith('sha256:')

const CheckpointSchema = z.object({
  seq:    z.number().int().min(0),
  digest: sha256,
})

export const IntegrityDocumentSchema = z.object({
  version:         z.literal('1.0'),
  algorithm:       z.literal('sha256'),
  last_checkpoint: CheckpointSchema.nullable(),
  files:           z.record(z.string(), z.string()),
})

// Integrity Chain — discriminated union of four entry types
const chainBase = z.object({
  seq: z.number().int().min(0),
  ts:  z.string().datetime(),
})

export const ChainGenesisSchema = chainBase.extend({
  type:         z.literal('genesis'),
  imprint_hash: sha256,
  prev_hash:    z.null(),
})

export const ChainEndureCommitSchema = chainBase.extend({
  type:                  z.literal('ENDURE_COMMIT'),
  evolution_auth_digest: sha256,
  files:                 z.record(z.string(), sha256),
  integrity_doc_hash:    sha256,
  prev_hash:             sha256,
})

export const ChainSeveranceCommitSchema = chainBase.extend({
  type:               z.literal('SEVERANCE_COMMIT'),
  skill_removed:      z.string().min(1),
  reason:             z.string().min(1),
  files:              z.record(z.string(), sha256),
  integrity_doc_hash: sha256,
  prev_hash:          sha256,
})

export const ChainModelChangeSchema = chainBase.extend({
  type:               z.literal('MODEL_CHANGE'),
  from:               z.string().min(1),
  to:                 z.string().min(1),
  files:              z.record(z.string(), sha256),
  integrity_doc_hash: sha256,
  prev_hash:          sha256,
})

export const IntegrityChainEntrySchema = z.discriminatedUnion('type', [
  ChainGenesisSchema,
  ChainEndureCommitSchema,
  ChainSeveranceCommitSchema,
  ChainModelChangeSchema,
])

export const AllowlistDataSchema = z.record(z.string(), z.literal(true))

export type IntegrityDocument   = z.infer<typeof IntegrityDocumentSchema>
export type ChainGenesis         = z.infer<typeof ChainGenesisSchema>
export type ChainEndureCommit    = z.infer<typeof ChainEndureCommitSchema>
export type ChainSeveranceCommit = z.infer<typeof ChainSeveranceCommitSchema>
export type ChainModelChange     = z.infer<typeof ChainModelChangeSchema>
export type IntegrityChainEntry  = z.infer<typeof IntegrityChainEntrySchema>
export type AllowlistData        = z.infer<typeof AllowlistDataSchema>
