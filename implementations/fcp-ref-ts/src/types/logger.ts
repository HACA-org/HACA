export type LogLevel = 'debug' | 'info' | 'warn' | 'error'

export interface LogEvent {
  readonly level: LogLevel
  readonly ts:    string
  readonly msg:   string
  readonly data?: unknown
}

export interface Logger {
  debug(msg: string, data?: unknown): void
  info(msg: string, data?: unknown): void
  warn(msg: string, data?: unknown): void
  error(msg: string, data?: unknown): void
  child(context: Record<string, unknown>): Logger
}
