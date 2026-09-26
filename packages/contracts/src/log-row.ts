import type { ServiceNameValue } from "./service-name.js";

export const ERROR_THRESHOLD = 500; // status_code >= this is an error
export const ERROR_MSG_MAX_LEN = 500;

export type LogRow = {
  timestamp: string;
  service: ServiceNameValue;
  endpoint: string;
  status_code: number;
  latency_ms: number;
  error_message: string | null;
  note: string | null;
  trace_id: string;
};

export function isError(statusCode: number): boolean {
  return statusCode >= ERROR_THRESHOLD;
}

export function errorMessage(
  text: string | null | undefined,
  statusCode: number,
): string | null {
  if (!isError(statusCode)) return null;
  if (text == null) return `error status ${statusCode}`;
  return String(text).slice(0, ERROR_MSG_MAX_LEN);
}

export function nowIso(): string {
  return new Date().toISOString();
}

export type MakeLogRowInput = {
  service: ServiceNameValue;
  endpoint: string;
  status_code: number;
  latency_ms: number;
  error_text?: string | null;
  note?: string | null;
  trace_id?: string;
};

export function makeLogRow(input: MakeLogRowInput): LogRow {
  return {
    timestamp: nowIso(),
    service: input.service,
    endpoint: input.endpoint,
    status_code: input.status_code,
    latency_ms: input.latency_ms,
    error_message: errorMessage(input.error_text ?? null, input.status_code),
    note: input.note ?? null,
    trace_id: input.trace_id ?? crypto.randomUUID(),
  };
}
