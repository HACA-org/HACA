import { z } from 'zod'

export const TopologySchema = z.enum(['transparent', 'opaque'])

export const OperatorBoundSchema = z.object({
  operatorName:  z.string().min(1),
  operatorEmail: z.string().email(),
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
    budgetTokens: z.number().int().positive(),
    criticalPct:  z.number().int().min(1).max(100),
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
})

export const ImprintRecordSchema = z.object({
  version:            z.literal('1.0'),
  activatedAt:        z.string().datetime(),
  hacaArchVersion:    z.string().min(1),
  hacaProfile:        z.string().min(1),
  operatorBound:      OperatorBoundSchema,
  structuralBaseline: z.string().startsWith('sha256:'),
  integrityDocument:  z.string().startsWith('sha256:'),
  skillsIndex:        z.string().startsWith('sha256:'),
})

export type Topology      = z.infer<typeof TopologySchema>
export type OperatorBound = z.infer<typeof OperatorBoundSchema>
export type Baseline      = z.infer<typeof BaselineSchema>
export type ImprintRecord = z.infer<typeof ImprintRecordSchema>
