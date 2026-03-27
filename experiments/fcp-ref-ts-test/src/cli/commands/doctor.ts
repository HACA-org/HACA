import type { Command } from 'commander'

export function registerDoctor(program: Command): void {
  program
    .command('doctor')
    .description('Check entity integrity')
    .option('--fix', 'Attempt to repair issues')
    .action(async (_opts: { fix?: boolean }) => {
      // TODO: SIL integrity check
      console.log('fcp doctor — not yet implemented')
    })
}
