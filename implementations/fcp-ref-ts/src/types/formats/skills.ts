import { z } from 'zod'

export const SkillClassSchema = z.enum(['custom', 'operator'])

const SkillEntrySchema = z.object({
  name:     z.string().min(1),
  desc:     z.string().min(1),
  manifest: z.string().min(1),
  class:    SkillClassSchema,
})

const AliasEntrySchema = z.object({
  skill:        z.string().min(1),
  operatorOnly: z.boolean().optional(),
})

export const SkillIndexSchema = z.object({
  version: z.literal('1.0'),
  skills:  z.array(SkillEntrySchema),
  aliases: z.record(z.string(), AliasEntrySchema),
})

export const SkillManifestSchema = z.object({
  name:           z.string().min(1),
  class:          SkillClassSchema,
  version:        z.string().min(1),
  description:    z.string().min(1),
  timeoutSeconds: z.number().int().positive(),
  background:     z.boolean(),
  ttlSeconds:     z.number().int().positive().nullable(),
  permissions:    z.array(z.string()),
  dependencies:   z.array(z.string()),
})

export type SkillClass    = z.infer<typeof SkillClassSchema>
export type SkillEntry    = z.infer<typeof SkillEntrySchema>
export type AliasEntry    = z.infer<typeof AliasEntrySchema>
export type SkillIndex    = z.infer<typeof SkillIndexSchema>
export type SkillManifest = z.infer<typeof SkillManifestSchema>
