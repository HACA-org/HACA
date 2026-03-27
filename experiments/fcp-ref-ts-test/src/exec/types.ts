export interface AllowlistData {
  shellRun?: string[]         // pre-approved commands (e.g. ["grep", "ls", "mkdir"])
  webFetch?: string[]         // pre-approved domains (e.g. ["github.com"])
  [tool: string]: string[] | true | undefined  // custom skills: string[] of args or true for blanket
}

export interface ExecContext {
  workspaceFocus: string | null
}
