import type { Command } from 'commander'

export function registerUpdate(program: Command): void {
  program
    .command('update')
    .description('Update CLI and installed entities')
    .option('--dry-run', 'Show what would be updated without applying')
    .action(async (_opts: { dryRun?: boolean }) => {
      // TODO: download tarball, update CLI, offer per-entity update
      console.log('fcp update — not yet implemented')
    })
}
