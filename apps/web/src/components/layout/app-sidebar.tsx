"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  RiDashboardLine,
  RiFlowChart,
  RiShieldCheckLine,
  RiHistoryLine,
  RiShieldLine,
  RiPlugLine,
} from "@remixicon/react";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarFooter,
} from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

const navItems = [
  {
    title: "Overview",
    href: "/",
    icon: RiDashboardLine,
  },
  {
    title: "Verification",
    href: "/verification",
    icon: RiShieldCheckLine,
  },
  {
    title: "Decision & Proposals",
    href: "/proposals",
    icon: RiFlowChart,
  },
  {
    title: "External Targets",
    href: "/targets",
    icon: RiPlugLine,
  },
  {
    title: "Audit Trail",
    href: "/audit",
    icon: RiHistoryLine,
  },
];

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="p-4">
        <div className="flex items-center gap-2.5">
          <div className="flex size-7 items-center justify-center bg-primary text-primary-foreground">
            <RiShieldLine className="size-4" />
          </div>
          <div className="flex flex-col group-data-[collapsible=icon]:hidden">
            <span className="text-sm font-semibold tracking-tight">GuardRail</span>
            <span className="text-[10px] text-muted-foreground leading-none">Canary Verifier</span>
          </div>
        </div>
      </SidebarHeader>

      <Separator />

      <SidebarContent className="pt-2">
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => {
                const active = pathname === item.href;
                return (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      render={<Link href={item.href} />}
                      isActive={active}
                      tooltip={item.title}
                      className={cn(
                        "gap-2.5 text-xs",
                        active && "font-medium",
                      )}
                    >
                      <item.icon className="size-4 shrink-0" />
                      <span>{item.title}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="p-4 group-data-[collapsible=icon]:hidden">
        <p className="text-[10px] text-muted-foreground">
          Governance-gated remediation
        </p>
      </SidebarFooter>
    </Sidebar>
  );
}
