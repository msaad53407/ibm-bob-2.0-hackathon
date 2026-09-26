// Barrel: preserves `import { X } from "@guardrail/contracts"`.
// New code may import service-name.js / log-row.js / proposal.js directly.
export { ServiceName } from "./service-name.js";
export type { ServiceNameValue } from "./service-name.js";
export {
  ERROR_THRESHOLD,
  ERROR_MSG_MAX_LEN,
  isError,
  errorMessage,
  nowIso,
  makeLogRow,
} from "./log-row.js";
export type { LogRow, MakeLogRowInput } from "./log-row.js";
export type { Verdict, Proposal } from "./proposal.js";
