import type { Command } from 'commander'

export function registerInit(program: Command): void {
  program
    .command('init')
    .description('Install or reset an entity')
    .option('--reset', 'Reset an existing entity')
    .action(async (_opts: { reset?: boolean }) => {
      // TODO: implement FAP / boot sequence
      console.log('fcp init — not yet implemented')
    })
}
