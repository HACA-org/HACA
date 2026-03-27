import type { Command } from 'commander'

export function registerRemove(program: Command): void {
  program
    .command('remove <entity_id>')
    .description('Uninstall an entity')
    .action(async (_entityId: string) => {
      // TODO: rm -rf ~/.fcp/entities/<entity_id> with confirmation
      console.log('fcp remove — not yet implemented')
    })
}
