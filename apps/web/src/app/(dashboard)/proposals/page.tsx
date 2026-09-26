import { ProposalsView } from "@/components/proposals/proposals-view";
import { PageHeader } from "@/components/shared/page-header";

export const dynamic = "force-dynamic";

export default async function ProposalsPage({
  searchParams,
}: {
  searchParams: Promise<{ target?: string }>;
}) {
  const { target } = await searchParams;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Decision & Proposals"
        description={
          target
            ? "Advisory verdict for a connected external pair — recommendations only."
            : "Run the Decision module against live Verification data. Review the ranked Proposal set and approve a Traffic flip."
        }
      />
      <ProposalsView targetId={target ?? null} />
    </div>
  );
}
