// MIL component entrypoint.
// Exposes: memory store, recall, closure processing, GC, tool handlers.
export { recall, createMemoryStore, processClosure } from './recall.js'
export { compactSessionHistory }                     from './gc.js'
export { getWorkingMemory, setWorkingMemory, mergeWorkingMemory } from './working.js'
export { writeSemantic, searchSemantic } from './semantic.js'
export { writeEpisodic, rotateEpisodic, searchEpisodic } from './episodic.js'

export { memoryRecallHandler }   from './tools/memory-recall.js'
export { memoryWriteHandler }    from './tools/memory-write.js'
export { closurePayloadHandler } from './tools/closure-payload.js'
