// Ordered registry of boot phases. boot.ts iterates this array — never hardcodes phase logic.
import type { BootPhase } from '../types/boot.js'
import { phase0 } from './phase0.js'
import { phase1 } from './phase1.js'
import { phase2 } from './phase2.js'
import { phase3 } from './phase3.js'
import { phase4 } from './phase4.js'
import { phase5 } from './phase5.js'
import { phase6 } from './phase6.js'
import { phase7 } from './phase7.js'

export const BOOT_PHASES: BootPhase[] = [
  phase0,
  phase1,
  phase2,
  phase3,
  phase4,
  phase5,
  phase6,
  phase7,
]
