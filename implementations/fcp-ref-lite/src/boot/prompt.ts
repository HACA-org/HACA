import { createInterface } from 'node:readline'

export function createPrompt() {
  const rl = createInterface({ input: process.stdin, output: process.stdout })

  function ask(question: string): Promise<string> {
    return new Promise(resolve => rl.question(question, answer => resolve(answer.trim())))
  }

  function close(): void {
    rl.close()
  }

  return { ask, close }
}
