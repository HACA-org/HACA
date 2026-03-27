import { z } from 'zod'

export const TopologySchema = z.enum(['transparent', 'opaque'])

export const OperatorBoundSchema = z.object({
  operator_name:  z.string().min(1),
  operator_email: z.string().email(),
  operator_hash:  z.string().startsWith('sha256:'),
})

export const BaselineSchema = z.object({
  version:   z.literal('1.0'),
  entity_id: z.string().min(1),
  cpe: z.object({
    topology: TopologySchema,
    backend:  z.string().min(1),
  }),
  heartbeat: z.object({
    cycle_threshold:  z.number().int().positive(),
    interval_seconds: z.number().int().positive(),
  }),
  watchdog: z.object({
    sil_threshold_seconds: z.number().int().positive(),
  }),
  context_window: z.object({
    budget_tokens: z.number().int().positive(),
    critical_pct:  z.number().int().min(1).max(100),
  }),
  drift: z.object({
    comparison_mechanism: z.literal('ncd-gzip-v1'),
    threshold:            z.number().min(0).max(1),
  }),
  session_store: z.object({
    rotation_threshold_bytes: z.number().int().positive(),
  }),
  working_memory: z.object({
    max_entries: z.number().int().positive(),
  }),
  integrity_chain: z.object({
    checkpoint_interval: z.number().int().positive(),
  }),
  pre_session_buffer: z.object({
    max_entries: z.number().int().positive(),
  }),
  operator_channel: z.object({
    notifications_dir: z.string().min(1),
  }),
  fault: z.object({
    n_boot:    z.number().int().positive(),
    n_channel: z.number().int().positive(),
    n_retry:   z.number().int().positive(),
  }),
})

export const ImprintRecordSchema = z.object({
  version:             z.literal('1.0'),
  activated_at:        z.string().datetime(),
  haca_arch_version:   z.string().min(1),
  haca_profile:        z.string().min(1),
  operator_bound:      OperatorBoundSchema,
  structural_baseline: z.string().startsWith('sha256:'),
  integrity_document:  z.string().startsWith('sha256:'),
  skills_index:        z.string().startsWith('sha256:'),
})

export type Topology      = z.infer<typeof TopologySchema>
export type OperatorBound = z.infer<typeof OperatorBoundSchema>
export type Baseline      = z.infer<typeof BaselineSchema>
export type ImprintRecord = z.infer<typeof ImprintRecordSchema>
