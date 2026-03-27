#!/usr/bin/env node
// FCP CLI entry point.
import { buildProgram } from './dispatch.js'
import { CLIError } from '../types/cli.js'

const program = buildProgram()

program.parseAsync(process.argv).catch((err: unknown) => {
  if (err instanceof CLIError) {
    process.stderr.write(`fcp: ${err.message}\n`)
    process.exit(err.exitCode)
  }
  process.stderr.write(`fcp: ${err instanceof Error ? err.message : String(err)}\n`)
  process.exit(1)
})
