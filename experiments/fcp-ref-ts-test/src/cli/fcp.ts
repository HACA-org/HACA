#!/usr/bin/env node
import { buildProgram } from './dispatch.js'

const program = buildProgram()
program.parseAsync(process.argv).catch((err: unknown) => {
  console.error(err instanceof Error ? err.message : String(err))
  process.exit(1)
})
