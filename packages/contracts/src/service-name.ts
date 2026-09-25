/** Canonical values for the logs.service field. All writers must use these. */
export const ServiceName = {
  STABLE: "stable",
  CANARY: "canary",
  PROXY_EVENT: "proxy",
  PROXY_TRAFFIC: (target: "stable" | "canary") => `proxy->${target}` as const,
} as const;

export type ServiceNameValue = "stable" | "canary" | "proxy" | `proxy->${string}`;
