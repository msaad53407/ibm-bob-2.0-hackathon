/**
 * Query key registry — single source of truth for cache invalidation.
 * All hooks and mutation onSuccess callbacks reference these constants.
 */
export const queryKeys = {
  health: ["agent", "health"] as const,
  proxyRoute: ["proxy", "route"] as const,
  proposals: ["proposals"] as const,
  proposalSet: (id: number) => ["proposals", id] as const,
  audit: ["audit"] as const,
  logs: (limit?: number) => ["logs", limit ?? 200] as const,
} as const;
