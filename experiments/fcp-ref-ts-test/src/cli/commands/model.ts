import type { Command } from 'commander'

export function registerModel(program: Command): void {
  program
    .command('model')
    .description('Interactive model picker')
    .action(async () => {
      // TODO: detectAvailableModels() + TUI picker
      console.log('fcp model — not yet implemented')
    })
}
