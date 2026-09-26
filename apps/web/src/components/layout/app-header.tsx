"use client";

import { RiMenuLine } from "@remixicon/react";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";

interface AppHeaderProps {
  title: string;
}

export function AppHeader({ title }: AppHeaderProps) {
  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b bg-background px-4">
      <SidebarTrigger className="size-7">
        <RiMenuLine className="size-4" />
      </SidebarTrigger>
      <Separator orientation="vertical" className="h-4" />
      <span className="text-sm font-medium">{title}</span>
    </header>
  );
}
