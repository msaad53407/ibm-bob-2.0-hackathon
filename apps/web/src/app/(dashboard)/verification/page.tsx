import { VerificationView } from "@/components/verification/verification-view";
import { PageHeader } from "@/components/shared/page-header";

export const dynamic = "force-dynamic";

export default async function VerificationPage({
  searchParams,
}: {
  searchParams: Promise<{ target?: string }>;
}) {
  const { target } = await searchParams;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Verification"
        description={
          target
            ? "Side-by-side comparison of your connected Stable and Canary — status codes, latency, and diffs from the Traffic-runner."
            : "Side-by-side comparison of Stable and Canary — status codes, latency, and diffs from the Traffic-runner."
        }
      />
      <VerificationView targetId={target ?? null} />
    </div>
  );
}
