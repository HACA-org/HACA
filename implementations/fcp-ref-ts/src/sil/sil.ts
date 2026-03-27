// SIL component entrypoint.
// Exposes: heartbeat, drift, endure, integrity, chain, tool handlers.
export { createHeartbeat, budgetCheck, focusCheck, inboxCheck, identityCheck } from './heartbeat.js'
export { runDriftEvaluation }  from './drift.js'
export { runEndureProtocol, readPendingProposals, approveProposal } from './endure.js'
export { verifyIntegrityDoc, verifyChainFromImprint, refreshIntegrityDoc } from './integrity.js'
export { readChain, appendEndureCommit, appendModelChange } from './chain.js'

export { SESSION_CLOSE_SIGNAL, sessionCloseHandler }   from './tools/session-close.js'
export { evolutionProposalHandler } from './tools/evolution-proposal.js'
