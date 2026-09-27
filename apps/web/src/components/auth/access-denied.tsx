"use client";

import { RiShieldLine } from "@remixicon/react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/components/auth/auth-provider";

/** Shown by the dashboard layout when the signed-in user is not allowlisted. */
export function AccessDenied({ email }: { email: string }) {
  const { signOut } = useAuth();

  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <div className="w-full max-w-sm rounded border bg-card p-6 text-center shadow-sm">
        <RiShieldLine className="mx-auto size-8 text-muted-foreground" />
        <h1 className="mt-3 text-base font-semibold">Not an admin</h1>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          Signed in as <strong className="text-foreground">{email}</strong>,
          which is not in the admins allowlist. Ask an existing admin to run{" "}
          <code className="rounded bg-muted px-1">
            insert into admins (email)
          </code>{" "}
          with your address.
        </p>
        <Button
          variant="outline"
          size="sm"
          className="mt-4"
          onClick={() => void signOut()}
        >
          Sign out
        </Button>
      </div>
    </div>
  );
}
