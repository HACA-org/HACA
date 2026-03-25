import { Command } from 'commander'
import { registerInit } from './commands/init.js'
import { registerList } from './commands/list.js'
import { registerStatus } from './commands/status.js'
import { registerModel } from './commands/model.js'
import { registerSet } from './commands/set.js'
import { registerRemove } from './commands/remove.js'
import { registerDoctor } from './commands/doctor.js'
import { registerEndure } from './commands/endure.js'
import { registerAgenda } from './commands/agenda.js'
import { registerUpdate } from './commands/update.js'

export function buildProgram(): Command {
  const program = new Command()

  program
    .name('fcp')
    .description('FCP — Cognitive Processing Framework')
    .version('0.1.0')
    .option('--tui', 'Boot with TUI (default)')
    .option('--verbose', 'Boot with verbose mode')
    .option('--debug', 'Boot with debug mode')
    .option('--auto <cron_id>', 'Run scheduled task in auto:session')
    .action(async (opts: { tui?: boolean; verbose?: boolean; debug?: boolean; auto?: string }) => {
      if (opts.auto) {
        // TODO: run auto:session for cron_id
        console.log(`fcp --auto ${opts.auto} — not yet implemented`)
        return
      }
      // TODO: resolve default entity + boot + TUI session
      console.log('fcp — boot not yet implemented')
    })

  registerInit(program)
  registerList(program)
  registerStatus(program)
  registerModel(program)
  registerSet(program)
  registerRemove(program)
  registerDoctor(program)
  registerEndure(program)
  registerAgenda(program)
  registerUpdate(program)

  return program
}
