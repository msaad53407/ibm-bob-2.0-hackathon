import { TargetsView } from "@/components/targets/targets-view";
import { PageHeader } from "@/components/shared/page-header";

export const dynamic = "force-dynamic";

export default function TargetsPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="External Targets"
        description="Connect your own stable + canary APIs with an OpenAPI spec. GuardRail generates edge cases, probes both versions, and advises — read-only on your traffic."
      />
      <TargetsView />
    </div>
  );
}
