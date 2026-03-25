import type { Command } from 'commander'

export function registerSet(program: Command): void {
  program
    .command('set <entity_id>')
    .description('Set default entity')
    .action(async (_entityId: string) => {
      // TODO: write ~/.fcp/default
      console.log('fcp set — not yet implemented')
    })

  program
    .command('unset')
    .description('Unset default entity')
    .action(async () => {
      // TODO: remove ~/.fcp/default
      console.log('fcp unset — not yet implemented')
    })
}
