// Generate a canonical baseline.json for a new entity.
import { randomUUID } from 'node:crypto'
import type { Topology, AuthorizationScope } from '../../types/formats/baseline.js'

export interface BaselineTemplateOpts {
  readonly entityId?:           string
  readonly topology:            Topology
  readonly backend:             string   // "<provider>:<model>"
  readonly fallbackTokens:      number
  readonly authorizationScope?: AuthorizationScope
}

export function makeBaselineJson(opts: BaselineTemplateOpts): Record<string, unknown> {
  return {
    version:  '1.0',
    entityId: opts.entityId ?? randomUUID(),
    cpe: {
      topology: opts.topology,
      backend:  opts.backend,
    },
    heartbeat: {
      cycleThreshold:  10,
      intervalSeconds: 300,
    },
    watchdog: {
      silThresholdSeconds: 600,
    },
    contextWindow: {
      fallbackTokens: opts.fallbackTokens,
      criticalPct:    80,
      warnPct:        65,
    },
    drift: {
      comparisonMechanism: 'ncd-gzip-v1',
      threshold:           opts.topology === 'transparent' ? 0.0 : 0.15,
    },
    sessionStore: {
      rotationThresholdBytes: 5_000_000,
    },
    workingMemory: {
      maxEntries: 50,
    },
    integrityChain: {
      checkpointInterval: 5,
    },
    preSessionBuffer: {
      maxEntries: 10,
    },
    operatorChannel: {
      notificationsDir: 'state/operator-notifications',
    },
    fault: {
      nBoot:    3,
      nChannel: 3,
      nRetry:   3,
    },
    ...(opts.authorizationScope ? { authorizationScope: opts.authorizationScope } : {}),
  }
}
