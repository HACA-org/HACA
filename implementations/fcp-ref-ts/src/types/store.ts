import * as path from 'node:path'

// All paths relative to entity root, computed once at startup and injected.
// No module-level state — createLayout returns a frozen plain object.
export interface Layout {
  readonly root: string
  readonly bootMd: string
  readonly persona: string
  readonly skills: {
    readonly dir: string
    readonly index: string
  }
  readonly hooks: string
  readonly io: {
    readonly inbox: string
    readonly presession: string
    readonly spool: string
  }
  readonly memory: {
    readonly dir: string
    readonly imprint: string
    readonly episodic: string
    readonly semantic: string
    readonly activeContext: string
    readonly sessionJsonl: string
    readonly workingMemory: string
    readonly sessionHandoff: string
  }
  readonly state: {
    readonly dir: string
    readonly baseline: string
    readonly integrity: string
    readonly integrityLog: string
    readonly integrityChain: string
    readonly driftProbes: string
    readonly semanticDigest: string
    readonly workspaceFocus: string
    readonly pendingClosure:   string
    readonly pendingProposals: string
    readonly sentinels: {
      readonly dir: string
      readonly sessionToken: string
    }
    readonly snapshots: string
    readonly operatorNotifications: string
    readonly distressBeacon: string
    readonly allowlist: string
    readonly sessionGrants: string
    readonly heartbeat: string
  }
}

export function createLayout(root: string): Layout {
  const j = (...parts: string[]): string => path.join(root, ...parts)
  return {
    root,
    bootMd:  j('boot.md'),
    persona: j('persona'),
    skills: {
      dir:   j('skills'),
      index: j('skills', 'index.json'),
    },
    hooks: j('hooks'),
    io: {
      inbox:      j('io', 'inbox'),
      presession: j('io', 'inbox', 'presession'),
      spool:      j('io', 'spool'),
    },
    memory: {
      dir:           j('memory'),
      imprint:       j('memory', 'imprint.json'),
      episodic:      j('memory', 'episodic'),
      semantic:      j('memory', 'semantic'),
      activeContext: j('memory', 'active-context'),
      sessionJsonl:  j('memory', 'session.jsonl'),
      workingMemory: j('memory', 'working-memory.json'),
      sessionHandoff: j('memory', 'session-handoff.json'),
    },
    state: {
      dir:                  j('state'),
      baseline:             j('state', 'baseline.json'),
      integrity:            j('state', 'integrity.json'),
      integrityLog:         j('state', 'integrity.log'),
      integrityChain:       j('state', 'integrity-chain.jsonl'),
      driftProbes:          j('state', 'drift-probes.jsonl'),
      semanticDigest:       j('state', 'semantic-digest.json'),
      workspaceFocus:       j('state', 'workspace-focus.json'),
      pendingClosure:       j('state', 'pending-closure.json'),
      pendingProposals:     j('state', 'pending-proposals.json'),
      sentinels: {
        dir:          j('state', 'sentinels'),
        sessionToken: j('state', 'sentinels', 'session.token'),
      },
      snapshots:            j('state', 'snapshots'),
      operatorNotifications: j('state', 'operator-notifications'),
      distressBeacon:       j('state', 'distress.beacon'),
      allowlist:            j('state', 'allowlist.json'),
      sessionGrants:        j('state', 'session-grants.json'),
      heartbeat:            j('state', 'heartbeat.json'),
    },
  }
}
