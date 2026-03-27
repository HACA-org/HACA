import type { Command } from 'commander'

export function registerAgenda(program: Command): void {
  program
    .command('agenda')
    .description('List scheduled tasks (no session needed)')
    .action(async () => {
      // TODO: read agenda/
      console.log('fcp agenda — not yet implemented')
    })
}
