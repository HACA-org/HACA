// Generate a canonical baseline.json for a new entity.
import { randomUUID } from 'node:crypto'
import type { Topology } from '../../types/formats/baseline.js'

export interface BaselineTemplateOpts {
  readonly entityId?:    string
  readonly topology:     Topology
  readonly backend:      string   // "<provider>:<model>"
  readonly budgetTokens: number
}

export function makeBaselineJson(opts: BaselineTemplateOpts): Record<string, unknown> {
  return {
    version:   '1.0',
    entity_id: opts.entityId ?? randomUUID(),
    cpe: {
      topology: opts.topology,
      backend:  opts.backend,
    },
    heartbeat: {
      cycle_threshold:  10,
      interval_seconds: 300,
    },
    watchdog: {
      sil_threshold_seconds: 600,
    },
    context_window: {
      budget_tokens: opts.budgetTokens,
      critical_pct:  80,
    },
    drift: {
      comparison_mechanism: 'ncd-gzip-v1',
      threshold:            opts.topology === 'transparent' ? 0.0 : 0.15,
    },
    session_store: {
      rotation_threshold_bytes: 5_000_000,
    },
    working_memory: {
      max_entries: 50,
    },
    integrity_chain: {
      checkpoint_interval: 5,
    },
    pre_session_buffer: {
      max_entries: 10,
    },
    operator_channel: {
      notifications_dir: 'state/operator_notifications',
    },
    fault: {
      n_boot:    3,
      n_channel: 3,
      n_retry:   3,
    },
  }
}
