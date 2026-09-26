import { redirect } from "next/navigation";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { AppHeader } from "@/components/layout/app-header";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { AccessDenied } from "@/components/auth/access-denied";
import { getSessionUser } from "@/lib/supabase-server";

/**
 * Dashboard gate (Slice B): login required, admin allowlist enforced.
 * The allowlist read uses the user's own JWT against the "own admin row"
 * RLS policy — no service key involved.
 */
export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { supabase, user } = await getSessionUser();
  if (!user?.email) redirect("/login");

  const { data: admin } = await supabase
    .from("admins")
    .select("email")
    .eq("email", user.email)
    .maybeSingle();

  if (!admin) {
    return (
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset className="flex flex-col min-h-0">
          <AppHeader title="GuardRail" />
          <AccessDenied email={user.email} />
        </SidebarInset>
      </SidebarProvider>
    );
  }

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="flex flex-col min-h-0">
        <AppHeader title="GuardRail" />
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </SidebarInset>
    </SidebarProvider>
  );
}
