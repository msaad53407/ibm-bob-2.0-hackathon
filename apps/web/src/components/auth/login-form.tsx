"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { RiShieldCheckLine, RiMailSendLine } from "@remixicon/react";
import { toast } from "sonner";
import { getSupabase } from "@/lib/supabase";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type Mode = "signin" | "signup" | "magic";

/** Admin login: password sign-in/up plus passwordless magic link. */
export function LoginForm() {
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [magicSent, setMagicSent] = useState(false);
  const router = useRouter();

  function done() {
    router.replace("/");
    router.refresh();
  }

  async function onPassword(e: React.FormEvent) {
    e.preventDefault();
    if (!email || !password) {
      toast.error("Enter both email and password.");
      return;
    }
    setPending(true);
    try {
      const sb = getSupabase();
      if (mode === "signup") {
        const { data, error } = await sb.auth.signUp({ email, password });
        if (error) throw error;
        if (!data.session) {
          // "Confirm email" is on in Supabase Auth: no session yet.
          toast.info("Account created — confirm via email, then sign in.");
          setMode("signin");
          return;
        }
        toast.success("Account created — you are signed in.");
      } else {
        const { error } = await sb.auth.signInWithPassword({ email, password });
        if (error) throw error;
        toast.success("Signed in.");
      }
      done();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setPending(false);
    }
  }

  async function onMagic(e: React.FormEvent) {
    e.preventDefault();
    if (!email) {
      toast.error("Enter your email first.");
      return;
    }
    setPending(true);
    try {
      const { error } = await getSupabase().auth.signInWithOtp({
        email,
        options: { emailRedirectTo: window.location.origin },
      });
      if (error) throw error;
      setMagicSent(true);
      toast.success("Magic link sent — check your inbox.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not send magic link.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="w-full max-w-sm rounded border bg-card p-6 shadow-sm">
      <div className="mb-5 flex items-center gap-2">
        <RiShieldCheckLine className="size-5 text-muted-foreground" />
        <div>
          <h1 className="text-base font-semibold">GuardRail admin login</h1>
          <p className="text-xs text-muted-foreground">
            Only allowlisted admins can view the dashboard.
          </p>
        </div>
      </div>

      <Tabs
        value={mode}
        onValueChange={(v) => {
          setMode(v as Mode);
          setMagicSent(false);
        }}
      >
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="signin">Sign in</TabsTrigger>
          <TabsTrigger value="signup">Sign up</TabsTrigger>
          <TabsTrigger value="magic">Magic link</TabsTrigger>
        </TabsList>

        <TabsContent value="signin">
          <form onSubmit={onPassword} className="mt-4 flex flex-col gap-3">
            <Input
              type="email"
              placeholder="admin@example.com"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <Input
              type="password"
              placeholder="Password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Button type="submit" disabled={pending}>
              {pending ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </TabsContent>

        <TabsContent value="signup">
          <form onSubmit={onPassword} className="mt-4 flex flex-col gap-3">
            <Input
              type="email"
              placeholder="admin@example.com"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <Input
              type="password"
              placeholder="Choose a password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Button type="submit" disabled={pending}>
              {pending ? "Creating account…" : "Create account"}
            </Button>
            <p className="text-[11px] text-muted-foreground">
              Your email must be allowlisted in the admins table before the
              dashboard grants access.
            </p>
          </form>
        </TabsContent>

        <TabsContent value="magic">
          {magicSent ? (
            <div className="mt-4 flex flex-col items-center gap-2 py-4 text-center">
              <RiMailSendLine className="size-6 text-muted-foreground" />
              <p className="text-sm">Link sent to {email}.</p>
              <p className="text-xs text-muted-foreground">
                Click it on this device to sign in.
              </p>
            </div>
          ) : (
            <form onSubmit={onMagic} className="mt-4 flex flex-col gap-3">
              <Input
                type="email"
                placeholder="admin@example.com"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <Button type="submit" disabled={pending}>
                {pending ? "Sending…" : "Send magic link"}
              </Button>
            </form>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
