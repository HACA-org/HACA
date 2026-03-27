import { ZodError } from 'zod'
import {
  ACPEnvelopeSchema,
  BaselineSchema,
  ImprintRecordSchema,
  IntegrityDocumentSchema,
  IntegrityChainEntrySchema,
  AllowlistDataSchema,
  SessionTokenSchema,
  WorkingMemorySchema,
  ClosurePayloadSchema,
  SemanticDigestSchema,
  DriftProbeSchema,
  SkillIndexSchema,
  SkillManifestSchema,
  SessionHandoffFileSchema,
} from '../types/formats/index.js'

export class ParseError extends Error {
  constructor(
    public readonly schema: string,
    public override readonly cause: ZodError,
  ) {
    super(`Invalid ${schema}: ${cause.message}`)
    this.name = 'ParseError'
  }
}

function makeParse<T>(name: string, schema: { parse: (data: unknown) => T }) {
  return (raw: unknown): T => {
    try {
      return schema.parse(raw)
    } catch (e: unknown) {
      if (e instanceof ZodError) throw new ParseError(name, e)
      throw e
    }
  }
}

export const parseACPEnvelope         = makeParse('ACPEnvelope',         ACPEnvelopeSchema)
export const parseBaseline            = makeParse('Baseline',            BaselineSchema)
export const parseImprintRecord       = makeParse('ImprintRecord',       ImprintRecordSchema)
export const parseIntegrityDocument   = makeParse('IntegrityDocument',   IntegrityDocumentSchema)
export const parseIntegrityChainEntry = makeParse('IntegrityChainEntry', IntegrityChainEntrySchema)
export const parseAllowlistData       = makeParse('AllowlistData',       AllowlistDataSchema)
export const parseSessionToken        = makeParse('SessionToken',        SessionTokenSchema)
export const parseWorkingMemory       = makeParse('WorkingMemory',       WorkingMemorySchema)
export const parseClosurePayload      = makeParse('ClosurePayload',      ClosurePayloadSchema)
export const parseSemanticDigest      = makeParse('SemanticDigest',      SemanticDigestSchema)
export const parseDriftProbe          = makeParse('DriftProbe',          DriftProbeSchema)
export const parseSkillIndex          = makeParse('SkillIndex',          SkillIndexSchema)
export const parseSkillManifest       = makeParse('SkillManifest',       SkillManifestSchema)
export const parseSessionHandoff      = makeParse('SessionHandoff',      SessionHandoffFileSchema)
