"use client";

import {
  RiFlashlightLine,
  RiAlertLine,
  RiCheckboxCircleLine,
  RiInformationLine,
  RiArrowRightLine,
} from "@remixicon/react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { VerdictBadge } from "@/components/shared/status-badges";
import {
  usePropose,
  useExecute,
  useProposals,
  useTargets,
} from "@/hooks/use-agent-queries";
import type { ProposalItem, ProposalSet } from "@/types/guardrail";

// ── Risk indicator ────────────────────────────────────────────────────────────

/** Human label per finding kind — the badge in place of an Execute button. */
const KIND_LABEL: Record<string, string> = {
  flip: "Executable",
  advisory_hold: "Advisory",
  canary_error: "Canary-only failure",
  latency_regress: "Latency regression",
  status_divergence: "Status divergence",
  shared_error: "Pre-existing",
  stable_error: "Stable-only failure",
};

function RiskBar({ risk }: { risk: number }) {
  const pct = Math.round(risk * 100);
  const color =
    pct === 0
      ? "bg-emerald-500"
      : pct < 30
        ? "bg-amber-400"
        : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 rounded-full bg-muted">
        <div
          className={`h-full rounded-full ${color} transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[10px] text-muted-foreground">{pct}%</span>
    </div>
  );
}

// ── Single proposal card ──────────────────────────────────────────────────────

interface ProposalCardProps {
  proposal: ProposalItem;
  proposalSetId: number;
  rank: number;
  /** Null in advisory mode (external targets): no traffic control available. */
  onExecute: ((target: "stable" | "canary") => void) | null;
  isPending: boolean;
  advisory?: boolean;
}

function ProposalCard({
  proposal,
  rank,
  onExecute,
  isPending,
  advisory = false,
}: ProposalCardProps) {
  const isExecutable = proposal.execute !== null && onExecute !== null;
  const label = KIND_LABEL[proposal.kind] ?? "Informational";

  return (
    <div className="rounded border bg-card p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border text-[10px] font-medium text-muted-foreground">
            {rank}
          </span>
          <div>
            <p className="text-sm font-medium leading-snug">{proposal.action}</p>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              <Badge variant={proposal.tier === "critical" ? "destructive" : "secondary"} className="text-[10px]">
                {proposal.tier}
              </Badge>
              <Badge variant="outline" className="font-mono text-[10px]">
                {proposal.kind}
              </Badge>
            </div>
            <div className="mt-2 flex flex-wrap gap-3 text-[10px] text-muted-foreground">
              <span className="flex items-center gap-1">
                <RiAlertLine className="size-3" />
                Blast radius: <strong className="text-foreground">{proposal.blast_radius}</strong>
              </span>
              <span className="flex items-center gap-1">
                <RiArrowRightLine className="size-3" />
                Reversibility: <strong className="text-foreground">{proposal.reversibility}</strong>
              </span>
            </div>
            <div className="mt-2">
              <p
                title="Severity of the finding this proposal addresses — derived from the evidence, not the chance the action fails."
                className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
              >
                Finding severity
              </p>
              <RiskBar risk={proposal.risk} />
            </div>
            {(proposal.evidence?.length ?? 0) > 0 && (
              <ul className="mt-2 space-y-0.5 border-l pl-2">
                {proposal.evidence!.map((e, i) => (
                  <li key={i} className="font-mono text-[10px] text-muted-foreground">
                    {e}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {isExecutable && onExecute ? (
          <Button
            size="sm"
            variant="default"
            disabled={isPending}
            onClick={() => onExecute(proposal.execute!.target)}
            className="shrink-0"
          >
            <RiFlashlightLine className="size-3.5" />
            Execute
          </Button>
        ) : (
          <Badge variant="outline" className="shrink-0 text-[10px]">
            <RiInformationLine className="size-3" />
            {advisory && proposal.execute !== null ? "Advisory" : label}
          </Badge>
        )}
      </div>
    </div>
  );
}

// ── Proposal set block ────────────────────────────────────────────────────────

interface ProposalSetBlockProps {
  set: ProposalSet;
  isLatest: boolean;
  advisory: boolean;
}

function ProposalSetBlock({ set, isLatest, advisory }: ProposalSetBlockProps) {
  const { mutate: execute, isPending } = useExecute();

  function handleExecute(target: "stable" | "canary") {
    if (!set.id) return;
    execute({ target, approver: "dashboard", proposal_id: set.id });
  }

  const isEscalate = set.verdict === "escalate";

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <VerdictBadge verdict={set.verdict} />
          {isLatest && (
            <Badge variant="outline" className="text-[10px]">Latest</Badge>
          )}
          {set.id && (
            <span className="text-[10px] text-muted-foreground">#{set.id}</span>
          )}
        </div>
        {set.created_at && (
          <span className="text-[10px] text-muted-foreground">
            {new Date(set.created_at).toLocaleString()}
          </span>
        )}
      </div>

      {/* Reasons */}
      {set.reasons?.length > 0 && (
        <div className="space-y-1">
          {set.reasons.map((r, i) => (
            <div key={i} className="flex items-start gap-2 text-xs">
              {isEscalate ? (
                <RiAlertLine className="mt-0.5 size-3.5 shrink-0 text-red-500" />
              ) : (
                <RiCheckboxCircleLine className="mt-0.5 size-3.5 shrink-0 text-emerald-500" />
              )}
              <span className="text-muted-foreground">{r}</span>
            </div>
          ))}
        </div>
      )}

      {/* Proposals */}
      {set.proposals?.length > 0 ? (
        <div className="space-y-2">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
            Proposals
          </p>
          {set.proposals.map((p, i) => (
            <ProposalCard
              key={i}
              proposal={p}
              proposalSetId={set.id!}
              rank={i + 1}
              onExecute={advisory ? null : handleExecute}
              isPending={isPending}
              advisory={advisory}
            />
          ))}
        </div>
      ) : (
        set.verdict === "keep" && (
          <div className="flex items-center gap-2 rounded border border-emerald-500/20 bg-emerald-500/5 px-3 py-2 text-xs text-emerald-600 dark:text-emerald-400">
            <RiCheckboxCircleLine className="size-4" />
            Canary is healthy — no remediation needed
          </div>
        )
      )}
    </div>
  );
}

// ── Public component ──────────────────────────────────────────────────────────

export function ProposalsView({ targetId }: { targetId?: string | null }) {
  const { data: proposals, isLoading, isFetching } = useProposals();
  const { mutate: propose, isPending: isProposing } = usePropose(targetId);
  const { data: targets } = useTargets();
  const advisory = !!targetId;

  const visible = (proposals ?? []).filter((s) =>
    targetId ? s.target_id === targetId : !s.target_id,
  );

  return (
    <div className="flex flex-col gap-6">
      {/* Actions bar */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <p className="text-xs text-muted-foreground">
          {advisory
            ? "Advisory verdict for the connected pair — recommendations only, no traffic control."
            : "Run the Decision module to generate a new ranked Proposal set. Approve a Proposal to execute the Traffic flip immediately."}
        </p>
        <div className="flex items-center gap-2">
          <select
            aria-label="Traffic scope"
            className="h-8 rounded-md border border-input bg-transparent px-2 text-xs"
            value={targetId ?? ""}
            onChange={(e) => {
              const v = e.target.value || null;
              const url = v ? `/proposals?target=${v}` : "/proposals";
              window.location.assign(url);
            }}
          >
            <option value="">Demo traffic</option>
            {(targets ?? []).map((t) => (
              <option key={t.id} value={t.id}>
                {t.stable_url} ↔ {t.canary_url}
              </option>
            ))}
          </select>
          <Button
            size="sm"
            onClick={() => propose()}
            disabled={isProposing || isFetching}
          >
            <RiFlashlightLine className="size-3.5" />
            {isProposing ? "Running…" : "Run Decision"}
          </Button>
        </div>
      </div>

      <Separator />

      {/* Proposal history */}
      {isLoading ? (
        <div className="space-y-4">
          {Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className="h-36 w-full" />
          ))}
        </div>
      ) : !visible.length ? (
        <div className="py-16 text-center">
          <p className="text-sm text-muted-foreground">
            No decisions yet — click <strong>Run Decision</strong> to start.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {visible.map((set, idx) => (
            <div key={set.id ?? idx}>
              <ProposalSetBlock set={set} isLatest={idx === 0} advisory={advisory} />
              {idx < visible.length - 1 && <Separator className="mt-6" />}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
