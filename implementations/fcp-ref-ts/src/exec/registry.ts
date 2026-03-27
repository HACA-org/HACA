// Tool handler registry — no module-level state (L2 compliant).
// Callers build a ToolHandler[] and pass it to createToolRegistry.
import type { ToolHandler } from '../types/exec.js'

export interface ToolRegistry {
  get(name: string):  ToolHandler | undefined
  list():             string[]
}

export function createToolRegistry(handlers: ToolHandler[]): ToolRegistry {
  const map = new Map(handlers.map(h => [h.name, h]))
  return {
    get:  (name) => map.get(name),
    list: ()     => [...map.keys()].sort(),
  }
}
