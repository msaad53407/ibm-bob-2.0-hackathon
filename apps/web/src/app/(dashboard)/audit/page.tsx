import { AuditTimeline } from "@/components/audit/audit-timeline";
import { PageHeader } from "@/components/shared/page-header";

export const dynamic = "force-dynamic";

export default function AuditPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Audit Trail"
        description="Append-only record of every Proposal, Decision, approver, and Execution outcome."
      />
      <AuditTimeline />
    </div>
  );
}
