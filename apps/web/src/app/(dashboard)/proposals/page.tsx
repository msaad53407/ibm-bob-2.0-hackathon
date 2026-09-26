import { ProposalsView } from "@/components/proposals/proposals-view";
import { PageHeader } from "@/components/shared/page-header";

export const dynamic = "force-dynamic";

export default function ProposalsPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Decision & Proposals"
        description="Run the Decision module against live Verification data. Review the ranked Proposal set and approve a Traffic flip."
      />
      <ProposalsView />
    </div>
  );
}
