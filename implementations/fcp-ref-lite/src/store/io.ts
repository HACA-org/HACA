import { readFile, writeFile, rename, unlink, mkdir } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { randomUUID } from 'node:crypto'

export { existsSync as fileExists }

export async function ensureDir(path: string): Promise<void> {
  await mkdir(path, { recursive: true })
}

export async function readJson<T>(path: string): Promise<T> {
  const raw = await readFile(path, 'utf8')
  return JSON.parse(raw) as T
}

export async function writeJson<T>(path: string, data: T): Promise<void> {
  const tmp = join(dirname(path), `.tmp-${randomUUID()}`)
  await ensureDir(dirname(path))
  await writeFile(tmp, JSON.stringify(data, null, 2), 'utf8')
  await rename(tmp, path)
}

export async function appendJsonl(path: string, entry: unknown): Promise<void> {
  await ensureDir(dirname(path))
  await writeFile(path, JSON.stringify(entry) + '\n', { flag: 'a', encoding: 'utf8' })
}

export async function readJsonl<T>(path: string): Promise<T[]> {
  if (!existsSync(path)) return []
  const raw = await readFile(path, 'utf8')
  return raw
    .split('\n')
    .filter(Boolean)
    .map(line => JSON.parse(line) as T)
}

export async function touchFile(path: string): Promise<void> {
  await ensureDir(dirname(path))
  await writeFile(path, '', { flag: 'wx' }).catch(() => {})
}

export async function removeFile(path: string): Promise<void> {
  await unlink(path).catch(() => {})
}
