import { cookies } from "next/headers";
import { createServerClient } from "@supabase/ssr";

/**
 * Server-side Supabase client (Slice B).
 * Reads the session from cookies; never mints service-role access.
 * In Server Components cookie writes are a no-op (no middleware refresh);
 * in Route Handlers use `createRouteSupabase` below so refreshed
 * auth cookies propagate onto the outgoing response.
 */
export async function createServerSupabase() {
  const cookieStore = await cookies();
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => cookieStore.getAll(),
        // Server Components cannot set cookies — session lives until expiry,
        // then the dashboard layout redirects to /login.
        setAll: () => {},
      },
    },
  );
}

/** The logged-in user, or null. Single place the dashboard gate reads identity. */
export async function getSessionUser() {
  const supabase = await createServerSupabase();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  return { supabase, user };
}
