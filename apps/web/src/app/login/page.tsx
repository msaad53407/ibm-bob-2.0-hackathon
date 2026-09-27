import { redirect } from "next/navigation";
import { LoginForm } from "@/components/auth/login-form";
import { getSessionUser } from "@/lib/supabase-server";

export const metadata = { title: "Login — GuardRail" };

/** Public route: signed-in admins bounce straight to the dashboard. */
export default async function LoginPage() {
  const { user } = await getSessionUser();
  if (user) redirect("/");

  return (
    <main className="flex min-h-screen w-full items-center justify-center bg-muted/40 p-6">
      <LoginForm />
    </main>
  );
}
