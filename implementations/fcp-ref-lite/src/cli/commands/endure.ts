import type { Command } from 'commander'

export function registerEndure(program: Command): void {
  program
    .command('endure')
    .description('Git sync and integrity chain')
    .option('--sync', 'Sync entity root with git remote')
    .option('--origin <url>', 'Set or update git remote origin')
    .option('--chain', 'Display integrity chain')
    .action(async (_opts: { sync?: boolean; origin?: string; chain?: boolean }) => {
      // TODO: SIL endure
      console.log('fcp endure — not yet implemented')
    })
}
