import { join } from 'node:path'

export type Layout = ReturnType<typeof createLayout>

export function createLayout(root: string) {
  const state = join(root, 'state')
  const memory = join(root, 'memory')
  const io = join(root, 'io')

  return {
    root,

    // Operator territory
    bootMd: join(root, 'BOOT.md'),
    distressBeacon: join(root, 'distress.beacon'),
    persona: join(root, 'persona'),
    skills: join(root, 'skills'),
    skillsIndex: join(root, 'skills', 'index.json'),
    hooks: join(root, 'hooks'),

    // IO
    io,
    inbox: join(io, 'inbox'),
    inboxPresession: join(io, 'inbox', 'presession'),
    notifications: join(io, 'notifications'),

    // Memory (MIL territory)
    memory,
    imprint: join(memory, 'imprint.json'),
    episodic: join(memory, 'episodic'),
    semantic: join(memory, 'semantic'),
    sessionStore: join(memory, 'session.jsonl'),
    workingMemory: join(memory, 'working-memory.json'),
    sessionHandoff: join(memory, 'session-handoff.json'),

    // State
    state,
    baseline: join(state, 'baseline.json'),
    integrity: join(state, 'integrity.json'),
    integrityChain: join(state, 'integrity-chain.jsonl'),
    entityLog: join(state, 'entity.log'),
    sessionToken: join(state, 'session.token'),
    pendingClosure: join(state, 'pending-closure.json'),
    allowlist: join(state, 'allowlist.json'),
    sessionGrants: join(state, 'session-grants.json'),

    // System territory (fcp-base protocol)
    protocol: join(root, 'src', 'protocol.md'),

    // Helper: path to a named skill
    skill: (name: string) => join(root, 'skills', name),
    skillManifest: (name: string) => join(root, 'skills', name, 'manifest.json'),
  } as const
}
