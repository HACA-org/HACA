// CPE (Cognitive Processing Engine) public entrypoint.
// External callers import resolveAdapter from here; internal adapter files
// import directly from their own modules.
export { resolveAdapter } from './resolve.js'
export { CPEConfigError, CPEInvokeError } from '../types/cpe.js'
export type { CPEAdapter, CPERequest, CPEResponse } from '../types/cpe.js'
