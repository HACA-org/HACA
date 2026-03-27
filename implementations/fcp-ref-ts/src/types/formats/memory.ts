import { z } from 'zod'

export const SessionTokenSchema = z.object({
  sessionId: z.string().uuid(),
  issuedAt:  z.string().datetime(),
  revokedAt: z.string().datetime().optional(),
})

export const WorkingMemoryEntrySchema = z.object({
  priority: z.number().int().min(1),
  path:     z.string().min(1),
})

export const WorkingMemorySchema = z.object({
  version: z.literal('1.0'),
  entries: z.array(WorkingMemoryEntrySchema),
})

const SessionHandoffSchema = z.object({
  pendingTasks: z.array(z.string()),
  nextSteps:    z.string(),
})

export const ClosurePayloadSchema = z.object({
  type:           z.literal('closure_payload'),
  consolidation:  z.string().min(1),
  promotion:      z.array(z.string()),
  workingMemory:  z.array(WorkingMemoryEntrySchema),
  sessionHandoff: SessionHandoffSchema,
})

export const SessionHandoffFileSchema = SessionHandoffSchema

export type SessionToken       = z.infer<typeof SessionTokenSchema>
export type WorkingMemoryEntry = z.infer<typeof WorkingMemoryEntrySchema>
export type WorkingMemory      = z.infer<typeof WorkingMemorySchema>
export type SessionHandoff     = z.infer<typeof SessionHandoffSchema>
export type ClosurePayload     = z.infer<typeof ClosurePayloadSchema>
