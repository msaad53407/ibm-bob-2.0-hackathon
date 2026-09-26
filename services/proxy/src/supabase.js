import { createClient } from "@supabase/supabase-js";

export function createSupabaseClient(url, key) {
  return url && key ? createClient(url, key) : null;
}
