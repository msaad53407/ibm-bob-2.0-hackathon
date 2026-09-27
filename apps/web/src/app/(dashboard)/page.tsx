import {
  RiShieldCheckLine,
  RiFlowChart,
  RiHistoryLine,
  RiArrowRightLine,
} from "@remixicon/react";
import Link from "next/link";
import { ProxyStatusCard, AgentHealthCard } from "@/components/dashboard/stat-cards";
import { RecentDecisionsCard } from "@/components/dashboard/recent-decisions";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";

const quickLinks = [
  {
    title: "Verification",
    description: "Live side-by-side log comparison for Stable and Canary.",
    href: "/verification",
    icon: RiShieldCheckLine,
  },
  {
    title: "Decision & Proposals",
    description: "Trigger the Decision module, review Proposals, and execute traffic flips.",
    href: "/proposals",
    icon: RiFlowChart,
  },
  {
    title: "Audit Trail",
    description: "Append-only record of every approved Execution.",
    href: "/audit",
    icon: RiHistoryLine,
  },
];

export default function OverviewPage() {
  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Overview"
        description="System health and recent activity at a glance."
      />

      {/* Status row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <ProxyStatusCard />
        <AgentHealthCard />
      </div>

      {/* Recent decisions */}
      <RecentDecisionsCard />

      {/* Quick links */}
      <div>
        <p className="mb-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Sections
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {quickLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="group flex flex-col gap-3 rounded border bg-card p-4 transition-colors hover:bg-muted/50"
            >
              <div className="flex items-center justify-between">
                <link.icon className="size-5 text-muted-foreground group-hover:text-foreground transition-colors" />
                <RiArrowRightLine className="size-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
              <div>
                <p className="text-sm font-medium">{link.title}</p>
                <p className="mt-0.5 text-xs text-muted-foreground leading-relaxed">
                  {link.description}
                </p>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
