// CLI command router — registers all subcommands.
import { Command } from 'commander'
import { registerInit }   from './commands/init.js'
import { registerRun, runFcp } from './commands/run.js'
import { registerStatus } from './commands/status.js'
import { registerDoctor } from './commands/doctor.js'
import { registerModel }    from './commands/model.js'
import { registerEntities } from './commands/entities.js'

export function buildProgram(): Command {
  const program = new Command()

  program
    .name('fcp')
    .description('Filesystem Cognitive Platform — HACA Reference Implementation')
    .version('1.0.0')
    .option('--entity <id>', 'Entity ID to operate on')
    .option('--verbose',     'Enable verbose output')
    // Default action (no subcommand): start a session
    .action(async (opts: { entity?: string; verbose?: boolean }) => {
      await runFcp(opts)
    })

  registerInit(program)
  registerRun(program)
  registerStatus(program)
  registerDoctor(program)
  registerModel(program)
  registerEntities(program)

  program
    .command('help')
    .description('Show this help message')
    .action(() => { program.help() })

  return program
}
