import { createHash } from 'node:crypto'
import { existsSync } from 'node:fs'
import { readdir, readFile } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import type { Layout } from '../store/layout.js'
import { readJson, writeJson, touchFile, removeFile, ensureDir } from '../store/io.js'
import { FAPError, type ImprintRecord, type OperatorBound } from './types.js'
import { createPrompt } from './prompt.js'
import type { Logger } from '../logger/logger.js'

function sha256(data: string): string {
  return 'sha256:' + createHash('sha256').update(data, 'utf8').digest('hex')
}

function sha256File(content: string): string {
  return sha256(content)
}

/** Tracks files created during FAP for rollback */
const created: string[] = []

async function safeWrite(path: string, data: unknown): Promise<void> {
  await writeJson(path, data)
  created.push(path)
}

async function rollback(): Promise<void> {
  for (const path of created.reverse()) {
    await removeFile(path)
  }
  created.length = 0
}

// Step 1: Validate structural prerequisites
async function validateStructure(layout: Layout): Promise<void> {
  if (!existsSync(layout.baseline)) {
    throw new FAPError('state/baseline.json not found', 1)
  }
  try {
    await readJson(layout.baseline)
  } catch {
    throw new FAPError('state/baseline.json is not valid JSON', 1)
  }

  if (!existsSync(layout.persona)) {
    throw new FAPError('persona/ directory not found', 1)
  }
  const personaFiles = await readdir(layout.persona)
  if (personaFiles.length === 0) {
    throw new FAPError('persona/ directory is empty', 1)
  }

  if (!existsSync(layout.bootMd)) {
    throw new FAPError('BOOT.md not found', 1)
  }
}

// Step 2: Validate baseline topology
async function validateTopology(layout: Layout, profile: 'haca-core' | 'haca-evolve'): Promise<void> {
  const baseline = await readJson<{ cpe?: { topology?: string } }>(layout.baseline)
  const topology = baseline.cpe?.topology ?? 'transparent'
  if (profile === 'haca-core' && topology !== 'transparent') {
    throw new FAPError('haca-core requires transparent topology', 2)
  }
}

// Step 3: Validate notifications channel is writable
async function validateChannel(layout: Layout): Promise<void> {
  await ensureDir(layout.notifications)
}

// Step 4: Operator enrollment (interactive)
async function enrollOperator(): Promise<OperatorBound> {
  const prompt = createPrompt()
  try {
    console.log('\nFCP — First Activation Protocol')
    console.log('This entity has not been activated yet.')
    console.log('Please provide operator details to bind this entity.\n')

    let confirmed = false
    let bound: OperatorBound | null = null

    while (!confirmed) {
      const name = await prompt.ask('Operator name: ')
      if (!name) throw new FAPError('Operator name is required', 4)

      const email = await prompt.ask('Operator email: ')
      if (!email) throw new FAPError('Operator email is required', 4)

      const hash = sha256(`${name}<${email}>`)
      bound = { name, email, hash }

      console.log(`\nOperator bound: ${name} <${email}>`)
      const confirm = await prompt.ask('Confirm? (y/n) [default: n]: ')
      confirmed = confirm.toLowerCase() === 'y'

      if (!confirmed) console.log('')
    }

    return bound!
  } finally {
    prompt.close()
  }
}

// Step 5: Build skill index + integrity document
async function buildIndexAndIntegrity(layout: Layout): Promise<{ skillsIndexHash: string; integrityHash: string }> {
  // Skill index — scan skills/ for manifests
  const skillsIndex: Record<string, unknown> = { skills: [] }
  if (existsSync(layout.skills)) {
    const entries = await readdir(layout.skills)
    const skills = []
    for (const entry of entries) {
      const manifest = layout.skillManifest(entry)
      if (existsSync(manifest)) {
        const data = await readJson(manifest)
        skills.push(data)
      }
    }
    skillsIndex['skills'] = skills
  }
  await safeWrite(layout.skillsIndex, skillsIndex)

  // Integrity document — hash vital files
  const vitals: Record<string, string> = {}
  const vitalPaths: Array<[string, string]> = [
    ['baseline', layout.baseline],
    ['bootMd', layout.bootMd],
    ['skillsIndex', layout.skillsIndex],
  ]
  for (const [key, path] of vitalPaths) {
    if (existsSync(path)) {
      const raw = await readFile(path, 'utf8')
      vitals[key] = sha256File(raw)
    }
  }
  const integrity = { version: '1.0', vitals, createdAt: new Date().toISOString() }
  await safeWrite(layout.integrity, integrity)

  return {
    skillsIndexHash: sha256File(JSON.stringify(skillsIndex)),
    integrityHash: sha256File(JSON.stringify(integrity)),
  }
}

// Step 6: Seal imprint record
async function sealImprint(
  layout: Layout,
  profile: 'haca-core' | 'haca-evolve',
  operatorBound: OperatorBound,
  baselineHash: string,
  integrityHash: string,
  skillsIndexHash: string,
): Promise<ImprintRecord> {
  const partial = {
    version: '1.0' as const,
    activatedAt: new Date().toISOString(),
    hacaProfile: profile,
    operatorBound,
    structuralBaseline: baselineHash,
    integrityDocument: integrityHash,
    skillsIndex: skillsIndexHash,
  }
  // Genesis Omega = SHA256 of the imprint itself
  const genesisOmega = sha256(JSON.stringify(partial))
  const imprint: ImprintRecord = { ...partial, genesisOmega }
  await safeWrite(layout.imprint, imprint)
  return imprint
}

// Step 7: Issue first session token
async function issueFirstToken(layout: Layout): Promise<string> {
  const sessionId = randomUUID()
  await touchFile(layout.sessionToken)
  return sessionId
}

// Step 8: Inject onboarding stimulus
async function injectOnboarding(layout: Layout, profile: 'haca-core' | 'haca-evolve'): Promise<void> {
  await ensureDir(layout.inboxPresession)
  const stimulus = {
    type: 'onboarding',
    profile,
    ts: new Date().toISOString(),
    message: profile === 'haca-core'
      ? 'Welcome. You are operating under haca-core: zero autonomy. All actions require explicit operator approval.'
      : 'Welcome. You are operating under haca-evolve: supervised autonomy. Actions within approved scope proceed without prompting.',
  }
  const path = `${layout.inboxPresession}/${randomUUID()}.json`
  await writeJson(path, stimulus)
}

export async function runFAP(
  layout: Layout,
  profile: 'haca-core' | 'haca-evolve',
  logger: Logger,
): Promise<string> {
  await logger.info('fap', 'start', { profile })

  try {
    // Step 1
    await validateStructure(layout)
    await logger.info('fap', 'step1_structure_ok')

    // Step 2
    await validateTopology(layout, profile)
    await logger.info('fap', 'step2_topology_ok')

    // Step 3
    await validateChannel(layout)
    await logger.info('fap', 'step3_channel_ok')

    // Step 4
    const operatorBound = await enrollOperator()
    await logger.info('fap', 'step4_operator_enrolled', { name: operatorBound.name })

    // Step 5
    const baselineRaw = JSON.stringify(await readJson(layout.baseline))
    const baselineHash = sha256File(baselineRaw)
    const { skillsIndexHash, integrityHash } = await buildIndexAndIntegrity(layout)
    await logger.info('fap', 'step5_index_integrity_built')

    // Step 6
    await sealImprint(layout, profile, operatorBound, baselineHash, integrityHash, skillsIndexHash)
    await logger.info('fap', 'step6_imprint_sealed')

    // Step 7
    const sessionId = await issueFirstToken(layout)
    await logger.info('fap', 'step7_token_issued', { sessionId })

    // Step 8
    await injectOnboarding(layout, profile)
    await logger.info('fap', 'step8_onboarding_injected')

    await logger.info('fap', 'complete')
    return sessionId
  } catch (err) {
    await logger.error('fap', 'rollback', { error: String(err) })
    await rollback()
    throw err
  }
}
