import { z } from 'zod'

export const TopologySchema = z.enum(['transparent', 'opaque'])

// HACA-Evolve only — Operator-defined authorization scope collected at FAP.
// Presence of this field is the canonical indicator that the entity runs HACA-Evolve.
export const AuthorizationScopeSchema = z.object({
  autonomousEvolution: z.boolean(),   // fileWrite / fileDelete / jsonMerge without approval
  autonomousSkills:    z.boolean(),   // skillInstall without approval
  operatorMemory:      z.boolean(),   // memory promotion without approval
  renewalDays:         z.number().int().min(0),  // 0 = no expiry
  grantedAt:           z.string().datetime(),
})

export const OperatorBoundSchema = z.object({
  operatorName:  z.string().min(1),
  operatorEmail: z.string().min(1),
  operatorHash:  z.string().startsWith('sha256:'),
})

export const BaselineSchema = z.object({
  version:  z.literal('1.0'),
  entityId: z.string().min(1),
  cpe: z.object({
    topology: TopologySchema,
    backend:  z.string().min(1),
  }),
  heartbeat: z.object({
    cycleThreshold:  z.number().int().positive(),
    intervalSeconds: z.number().int().positive(),
  }),
  watchdog: z.object({
    silThresholdSeconds: z.number().int().positive(),
  }),
  contextWindow: z.object({
    fallbackTokens: z.number().int().positive(),
    criticalPct:    z.number().int().min(1).max(100),
    warnPct:        z.number().int().min(1).max(100),
  }),
  drift: z.object({
    comparisonMechanism: z.literal('ncd-gzip-v1'),
    threshold:           z.number().min(0).max(1),
  }),
  sessionStore: z.object({
    rotationThresholdBytes: z.number().int().positive(),
  }),
  workingMemory: z.object({
    maxEntries: z.number().int().positive(),
  }),
  integrityChain: z.object({
    checkpointInterval: z.number().int().positive(),
  }),
  preSessionBuffer: z.object({
    maxEntries: z.number().int().positive(),
  }),
  operatorChannel: z.object({
    notificationsDir: z.string().min(1),
  }),
  fault: z.object({
    nBoot:    z.number().int().positive(),
    nChannel: z.number().int().positive(),
    nRetry:   z.number().int().positive(),
  }),
  // HACA-Evolve only — absent means HACA-Core (explicit approval required per proposal).
  authorizationScope: AuthorizationScopeSchema.optional(),
})

export const ImprintRecordSchema = z.object({
  version:            z.literal('1.0'),
  activatedAt:        z.string().datetime(),
  fcpVersion:         z.string().min(1),
  hacaArchVersion:    z.string().min(1),
  hacaProfile:        z.string().min(1),
  operatorBound:      OperatorBoundSchema,
  structuralBaseline: z.string().startsWith('sha256:'),
  integrityDocument:  z.string().startsWith('sha256:'),
  skillsIndex:        z.string().startsWith('sha256:'),
})

export type Topology           = z.infer<typeof TopologySchema>
export type AuthorizationScope = z.infer<typeof AuthorizationScopeSchema>
export type OperatorBound      = z.infer<typeof OperatorBoundSchema>
export type Baseline           = z.infer<typeof BaselineSchema>
export type ImprintRecord      = z.infer<typeof ImprintRecordSchema>
