import { existsSync } from 'node:fs'
import { readJson, writeJson } from '../store/io.js'
import type { Layout } from '../store/layout.js'
import type { AllowlistData } from './types.js'

export async function readAllowlist(layout: Layout): Promise<AllowlistData> {
  if (!existsSync(layout.allowlist)) return {}
  return readJson<AllowlistData>(layout.allowlist).catch(() => ({}))
}

export async function addToAllowlist(
  layout: Layout,
  tool: string,
  value: string,
): Promise<void> {
  const data = await readAllowlist(layout)
  if (data[tool] === true) return
  const current = Array.isArray(data[tool]) ? data[tool] : []
  if (!current.includes(value)) {
    await writeJson(layout.allowlist, { ...data, [tool]: [...current, value] })
  }
}

export function isCommandAllowed(data: AllowlistData, command: string): boolean {
  const list = data.shellRun
  if (!list) return false
  const cmd = command.trim().split(/\s+/)[0] ?? ''
  return list.includes(cmd)
}

export function isDomainAllowed(data: AllowlistData, url: string): boolean {
  const list = data.webFetch
  if (!list) return false
  try {
    const { hostname } = new URL(url)
    return list.some(d => hostname === d || hostname.endsWith('.' + d))
  } catch {
    return false
  }
}

export function isToolAllowed(data: AllowlistData, tool: string): boolean {
  const entry = data[tool]
  return entry === true || (Array.isArray(entry) && entry.length > 0)
}
