import type { Logger, LogLevel } from '../types/logger.js'

function formatEntry(
  level: LogLevel,
  msg: string,
  data: unknown,
  context: Record<string, unknown>,
): string {
  const entry: Record<string, unknown> = {
    ...context,
    level,
    ts: new Date().toISOString(),
    msg,
  }
  if (data !== undefined) entry['data'] = data
  return JSON.stringify(entry) + '\n'
}

export function createLogger(context: Record<string, unknown> = {}): Logger {
  const emit = (level: LogLevel, msg: string, data?: unknown): void => {
    process.stderr.write(formatEntry(level, msg, data, context))
  }
  return {
    debug: (msg, data) => emit('debug', msg, data),
    info:  (msg, data) => emit('info',  msg, data),
    warn:  (msg, data) => emit('warn',  msg, data),
    error: (msg, data) => emit('error', msg, data),
    child: (extra)     => createLogger({ ...context, ...extra }),
  }
}
