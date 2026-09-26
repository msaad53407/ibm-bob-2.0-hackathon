"use client";

import { RiLogoutBoxLine, RiUserLine } from "@remixicon/react";
import { useAuth } from "@/components/auth/auth-provider";
import { Button } from "@/components/ui/button";

/** Signed-in admin identity + sign out, for the dashboard header. */
export function UserMenu() {
  const { user, loading, signOut } = useAuth();

  if (loading || !user) return null;

  return (
    <div className="flex items-center gap-2">
      <span className="hidden items-center gap-1.5 text-xs text-muted-foreground sm:flex">
        <RiUserLine className="size-3.5" />
        {user.email}
      </span>
      <Button variant="ghost" size="sm" onClick={() => void signOut()}>
        <RiLogoutBoxLine className="size-3.5" />
        Sign out
      </Button>
    </div>
  );
}
