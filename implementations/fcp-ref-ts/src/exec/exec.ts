// EXEC component entrypoint.
// Exposes: tool handlers, allowlist policy, registry, dispatch.
export { loadAllowlistPolicy }  from './allowlist.js'
export { createToolRegistry }   from './registry.js'
export { dispatch }             from './dispatch.js'

export { fileReadHandler }    from './tools/file-read.js'
export { fileWriteHandler }   from './tools/file-write.js'
export { shellRunHandler }    from './tools/shell-run.js'
export { webFetchHandler }    from './tools/web-fetch.js'
export { agentRunHandler }    from './tools/agent-run.js'
export { skillCreateHandler } from './tools/skill-create.js'
export { skillAuditHandler }  from './tools/skill-audit.js'
