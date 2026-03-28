import * as fs from 'node:fs/promises'
import * as path from 'node:path'

export class IOError extends Error {
  constructor(
    public readonly op: 'read' | 'write' | 'append' | 'rename' | 'mkdir' | 'delete',
    public readonly filePath: string,
    message: string,
    public override readonly cause?: unknown,
  ) {
    super(message)
    this.name = 'IOError'
  }
}

export async function ensureDir(dirPath: string): Promise<void> {
  try {
    await fs.mkdir(dirPath, { recursive: true })
  } catch (e: unknown) {
    throw new IOError('mkdir', dirPath, `Cannot create directory: ${dirPath}`, e)
  }
}

export async function fileExists(filePath: string): Promise<boolean> {
  try {
    await fs.access(filePath)
    return true
  } catch {
    return false
  }
}

export async function readJson(filePath: string): Promise<unknown> {
  let content: string
  try {
    content = await fs.readFile(filePath, 'utf8')
  } catch (e: unknown) {
    throw new IOError('read', filePath, `Cannot read file: ${filePath}`, e)
  }
  try {
    return JSON.parse(content) as unknown
  } catch (e: unknown) {
    throw new IOError('read', filePath, `Malformed JSON: ${filePath}`, e)
  }
}

// Atomic write: tmp sibling → rename. Direct in-place writes are not permitted.
// Ensures parent directory exists before writing.
export async function atomicWrite(filePath: string, content: string): Promise<void> {
  const dir = path.dirname(filePath)
  const tmp = filePath + '.tmp'
  try {
    await fs.mkdir(dir, { recursive: true })
    await fs.writeFile(tmp, content, 'utf8')
    await fs.rename(tmp, filePath)
  } catch (e: unknown) {
    await fs.unlink(tmp).catch(() => undefined)
    throw new IOError('write', filePath, `Atomic write failed: ${filePath}`, e)
  }
}

// For structured state files (.json). Never use for append-only logs.
export async function writeJson(filePath: string, data: unknown): Promise<void> {
  await atomicWrite(filePath, JSON.stringify(data, null, 2) + '\n')
}

// For append-only logs (.jsonl). Never use for state files — it does NOT overwrite.
export async function appendJsonl(filePath: string, data: unknown): Promise<void> {
  try {
    await fs.appendFile(filePath, JSON.stringify(data) + '\n', 'utf8')
  } catch (e: unknown) {
    throw new IOError('append', filePath, `Cannot append to JSONL: ${filePath}`, e)
  }
}

export async function readJsonl(filePath: string): Promise<unknown[]> {
  let content: string
  try {
    content = await fs.readFile(filePath, 'utf8')
  } catch (e: unknown) {
    throw new IOError('read', filePath, `Cannot read JSONL: ${filePath}`, e)
  }
  return content
    .split('\n')
    .filter(line => line.trim().length > 0)
    .map((line, i) => {
      try {
        return JSON.parse(line) as unknown
      } catch (e: unknown) {
        throw new IOError('read', filePath, `Malformed JSON at line ${i + 1}: ${filePath}`, e)
      }
    })
}

// Read all .msg files from a directory in ascending ts order (ties by filename).
// Returns empty array if the directory does not exist.
export async function drainMsgDir(dirPath: string): Promise<{ file: string; raw: unknown }[]> {
  let entries: string[]
  try {
    entries = await fs.readdir(dirPath)
  } catch (e: unknown) {
    if (typeof e === 'object' && e !== null && (e as NodeJS.ErrnoException).code === 'ENOENT') {
      return []
    }
    throw new IOError('read', dirPath, `Cannot read inbox directory: ${dirPath}`, e)
  }
  const msgs = entries
    .filter(name => name.endsWith('.msg') || name.endsWith('.json'))
    .sort()
    .map(name => path.join(dirPath, name))

  const results: { file: string; raw: unknown }[] = []
  for (const file of msgs) {
    results.push({ file, raw: await readJson(file) })
  }
  return results
}

export async function deleteFile(filePath: string): Promise<void> {
  try {
    await fs.unlink(filePath)
  } catch (e: unknown) {
    throw new IOError('delete', filePath, `Cannot delete file: ${filePath}`, e)
  }
}

// Reads a JSONL file, returning an empty array if the file does not exist.
export async function readJsonlOrEmpty(filePath: string): Promise<unknown[]> {
  try {
    return await readJsonl(filePath)
  } catch (e: unknown) {
    if (e instanceof IOError && typeof e.cause === 'object' && e.cause !== null
        && (e.cause as NodeJS.ErrnoException).code === 'ENOENT') {
      return []
    }
    throw e
  }
}
