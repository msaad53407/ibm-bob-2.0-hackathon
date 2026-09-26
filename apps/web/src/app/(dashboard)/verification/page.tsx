import { VerificationView } from "@/components/verification/verification-view";
import { PageHeader } from "@/components/shared/page-header";

export const dynamic = "force-dynamic";

export default function VerificationPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Verification"
        description="Side-by-side comparison of Stable and Canary — status codes, latency, and diffs from the Traffic-runner."
      />
      <VerificationView />
    </div>
  );
}
