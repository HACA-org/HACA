// CPE (Cognitive Processing Engine) adapter contract.
// Adapters know nothing about Boot, Session, or Layout — they receive a
// CPERequest and return a CPEResponse. All provider-specific normalization
// happens inside the adapter.

export type MessageRole = 'user' | 'assistant'

export interface TextBlock {
  type: 'text'
  text: string
}

export interface ToolUseBlock {
  type:  'tool_use'
  id:    string
  name:  string
  input: unknown
}

export interface ToolResultBlock {
  type:        'tool_result'
  tool_use_id: string
  content:     string
}

export type ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock

export interface CPEMessage {
  role:    MessageRole
  content: string | ContentBlock[]
}

export interface CPEToolDeclaration {
  name:         string
  description:  string
  input_schema: Record<string, unknown>
}

export interface CPERequest {
  system?:  string
  messages: CPEMessage[]
  tools:    CPEToolDeclaration[]
}

export interface CPEUsage {
  inputTokens:  number
  outputTokens: number
}

export type StopReason = 'tool_use' | 'end_turn' | 'max_tokens' | 'stop_sequence'

export interface CPEResponse {
  stopReason: StopReason
  content:    string
  toolUses:   ToolUseBlock[]
  usage:      CPEUsage
}

export interface CPEAdapter {
  readonly provider:      string
  readonly model:         string
  readonly contextWindow: number
  invoke(req: CPERequest): Promise<CPEResponse>
}

export class CPEConfigError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'CPEConfigError'
  }
}

export class CPEInvokeError extends Error {
  constructor(
    message: string,
    public readonly statusCode?: number,
    public override readonly cause?: unknown,
  ) {
    super(message)
    this.name = 'CPEInvokeError'
  }
}
