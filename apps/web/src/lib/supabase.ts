import type { SupabaseClient } from "@supabase/supabase-js";
import { createBrowserClient } from "@supabase/ssr";

let _client: SupabaseClient | undefined;

/**
 * Lazy singleton Supabase client for the browser.
 * Uses cookie storage (via @supabase/ssr) so the session is visible to
 * Server Components / Route Handlers through `cookies()` — plain
 * `createClient` keeps it in localStorage, which the server can't see
 * (that caused the login → redirect-to-login loop).
 * Deferred so module evaluation during SSR/prerender doesn't throw when
 * NEXT_PUBLIC_SUPABASE_URL is not set at build time.
 */
export function getSupabase(): SupabaseClient {
  if (!_client) {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    if (!url || !key) {
      throw new Error(
        "Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY",
      );
    }
    _client = createBrowserClient(url, key);
  }
  return _client;
}

/** @deprecated Use getSupabase() — avoids build-time module-level evaluation. */
export const supabase = {
  get from() { return getSupabase().from.bind(getSupabase()); },
  get channel() { return getSupabase().channel.bind(getSupabase()); },
  get removeChannel() { return getSupabase().removeChannel.bind(getSupabase()); },
};
