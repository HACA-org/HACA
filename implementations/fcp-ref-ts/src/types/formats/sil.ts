import { z } from 'zod'

const ProbeScoreSchema = z.object({
  lastScore: z.number().min(0).max(1),
  meanScore: z.number().min(0).max(1),
  maxScore:  z.number().min(0).max(1),
})

export const SemanticDigestSchema = z.object({
  version:         z.literal('1.0'),
  lastUpdated:     z.string().datetime(),
  cyclesEvaluated: z.number().int().min(0),
  probes:          z.record(z.string(), ProbeScoreSchema),
})

const DeterministicLayerSchema = z.object({
  type:  z.enum(['hash', 'string', 'pattern']),
  value: z.string().min(1),
})

export const DriftProbeSchema = z.object({
  id:            z.string().min(1),
  description:   z.string().min(1),
  target:        z.string().startsWith('memory/'),
  deterministic: DeterministicLayerSchema.nullable(),
  reference:     z.string().nullable(),
})

export type ProbeScore     = z.infer<typeof ProbeScoreSchema>
export type SemanticDigest = z.infer<typeof SemanticDigestSchema>
export type DriftProbe     = z.infer<typeof DriftProbeSchema>
