import { QueryClient } from "@tanstack/react-query";

/** Singleton factory — one instance per app; never re-created on re-render. */
export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // 30s stale time — dashboard data is real-time via Supabase subscriptions
        // or refreshed manually; we don't want background refetch noise.
        staleTime: 30_000,
        retry: 1,
        refetchOnWindowFocus: false,
      },
    },
  });
}
