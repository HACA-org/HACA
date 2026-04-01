// Dynamic area — manages the 5-line content region below the footer.
// Supports a content stack with optional auto-expiry for transient notifications.
import type { DynamicContent, DynamicContentType } from '../types/tui.js'

const MAX_LINES = 5

export class DynamicArea {
  private content: DynamicContent | null = null

  // Replace current content.
  set(type: DynamicContentType, lines: string[], ttlMs?: number): void {
    this.content = ttlMs
      ? { type, lines: lines.slice(0, MAX_LINES), expiresAt: Date.now() + ttlMs }
      : { type, lines: lines.slice(0, MAX_LINES) }
  }

  // Clear all content.
  clear(): void {
    this.content = null
  }

  // Return current lines (up to 5). Expired content is auto-cleared.
  lines(): string[] {
    if (this.content?.expiresAt && Date.now() > this.content.expiresAt) {
      this.content = null
    }
    const raw = this.content?.lines ?? []
    const result = [...raw]
    while (result.length < MAX_LINES) result.push('')
    return result
  }

  // Current content type (or null if empty).
  get currentType(): DynamicContentType | null {
    if (this.content?.expiresAt && Date.now() > this.content.expiresAt) {
      this.content = null
    }
    return this.content?.type ?? null
  }
}
