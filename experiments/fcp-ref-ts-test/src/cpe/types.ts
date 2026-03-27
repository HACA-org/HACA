export type Profile = 'haca-core' | 'haca-evolve'
export type Topology = 'transparent' | 'opaque'
export type StopReason = 'end_turn' | 'tool_use' | 'max_tokens' | 'error'

export interface Message {
  role: 'user' | 'assistant'
  content: string | ContentBlock[]
}

export type ContentBlock =
  | { type: 'text'; text: string }
  | { type: 'tool_use'; id: string; name: string; input: Record<string, unknown> }
  | { type: 'tool_result'; tool_use_id: string; content: string }

export interface ToolDefinition {
  name: string
  description: string
  input_schema: Record<string, unknown>
}

export interface ToolUseCall {
  id: string
  name: string
  input: Record<string, unknown>
}

export interface CPERequest {
  system: string
  messages: Message[]
  tools?: ToolDefinition[]
  topology?: Topology
  maxTokens?: number
}

export interface CPEResponse {
  content: string | null
  toolCalls: ToolUseCall[]
  usage: { inputTokens: number; outputTokens: number }
  stopReason: StopReason
}

export interface CPEAdapter {
  readonly provider: string
  invoke(request: CPERequest): Promise<CPEResponse>
}

export interface ModelInfo {
  id: string
  provider: string
  contextWindow: number
}
