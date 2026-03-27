import type { Command } from 'commander'

export function registerStatus(program: Command): void {
  program
    .command('status')
    .description('Entity status overview (no session needed)')
    .action(async () => {
      // TODO: read state/ and logger counters
      console.log('fcp status — not yet implemented')
    })
}
