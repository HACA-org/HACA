// SIL component entrypoint.
// Exposes: heartbeat, drift, endure, integrity, chain, tool handlers.
export { createHeartbeat, budgetCheck, focusCheck, inboxCheck, identityCheck } from './heartbeat.js'
export { compactCheck, COMPACT_THRESHOLD_PCT } from './checks/compact.js'
export { runDriftEvaluation }  from './drift.js'
export { runEndureProtocol, readPendingProposals, approveProposal } from './endure.js'
export { verifyIntegrityDoc, verifyChainFromImprint, refreshIntegrityDoc } from './integrity.js'
export { readChain, appendEndureCommit, appendModelChange } from './chain.js'

export { SESSION_CLOSE_SIGNAL, sessionCloseHandler }   from './tools/session-close.js'
export { evolutionProposalHandler } from './tools/evolution-proposal.js'

// Signal string written to inbox to request session compaction.
export const COMPACT_SESSION_SIGNAL = '__fcp_compact_session__'
