import { z } from "zod";

// ── Config adapter ──────────────────────────────────────────────────────────
// Fails fast at startup with a clear message rather than a cryptic runtime error.
export const EnvSchema = z.object({
  PORT:                 z.coerce.number().int().positive().default(8080),
  STABLE_URL:           z.string().url().default("http://stable:8000"),
  CANARY_URL:           z.string().url().default("http://canary:8000"),
  SUPABASE_URL:         z.string().url({ message: "SUPABASE_URL must be a valid URL" }),
  SUPABASE_SERVICE_KEY: z.string().min(1, { message: "SUPABASE_SERVICE_KEY is required" }),
});

export function parseEnv(source) {
  const result = EnvSchema.safeParse(source);
  if (!result.success) {
    console.error("❌  Missing or invalid environment variables:\n");
    for (const issue of result.error.issues) {
      console.error(`  ${issue.path.join(".")}: ${issue.message}`);
    }
    process.exit(1);
  }
  return result.data;
}
