export { createCPE, resolveAdapter, createPairingAdapter, detectAvailableModels, type CPEConfig } from './cpe.js'
export { loadEnv, getEnv, requireEnv } from './env.js'
export { detectOllama, listOllamaModels } from './adapters/ollama.js'
export type { CPEAdapter, CPERequest, CPEResponse, Message, ContentBlock, ToolDefinition, ToolUseCall, ModelInfo, Profile, Topology, StopReason } from './types.js'
