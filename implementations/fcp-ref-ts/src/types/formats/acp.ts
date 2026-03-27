import { z } from 'zod'

export const ACPActorSchema = z.enum(['fcp', 'sil', 'mil', 'cpe', 'exec', 'operator'])

export const ACPTypeSchema = z.enum([
  'MSG',
  'SKILL_REQUEST',
  'SKILL_RESULT',
  'SKILL_ERROR',
  'SKILL_TIMEOUT',
  'HEARTBEAT',
  'DRIFT_FAULT',
  'IDENTITY_DRIFT',
  'EVOLUTION_PROPOSAL',
  'EVOLUTION_AUTH',
  'EVOLUTION_REJECTED',
  'PROPOSAL_PENDING',
  'ENDURE_COMMIT',
  'SEVERANCE_COMMIT',
  'SEVERANCE_PENDING',
  'SLEEP_COMPLETE',
  'ACTION_LEDGER',
  'SIL_UNRESPONSIVE',
  'CTX_SKIP',
  'CRITICAL_CLEARED',
  'DECOMMISSION',
  'MEMORY_RESULT',
  'MODEL_CHANGE',
])

export const ACPEnvelopeSchema = z.object({
  actor: ACPActorSchema,
  gseq:  z.number().int().positive(),
  tx:    z.string().uuid(),
  seq:   z.number().int().min(1),
  eof:   z.boolean(),
  type:  ACPTypeSchema,
  ts:    z.string().datetime(),
  data:  z.string().max(4000),
  crc:   z.string().regex(/^[0-9a-f]{8}$/),
})

export type ACPActor    = z.infer<typeof ACPActorSchema>
export type ACPType     = z.infer<typeof ACPTypeSchema>
export type ACPEnvelope = z.infer<typeof ACPEnvelopeSchema>
