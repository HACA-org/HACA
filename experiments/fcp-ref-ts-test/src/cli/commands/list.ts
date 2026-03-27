import type { Command } from 'commander'

export function registerList(program: Command): void {
  program
    .command('list')
    .description('List installed entities')
    .action(async () => {
      // TODO: read ~/.fcp/entities/
      console.log('fcp list — not yet implemented')
    })
}
