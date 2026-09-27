"use client";

import { useState } from "react";
import {
  RiPlugLine,
  RiPlayLine,
  RiCheckboxCircleLine,
  RiAlertLine,
} from "@remixicon/react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useTargets,
  useCreateTarget,
  useTargetCases,
  useTrafficRun,
} from "@/hooks/use-agent-queries";
import { useLogs } from "@/hooks/use-logs";
import type { TargetPair } from "@/types/guardrail";

// ── Connect form ─────────────────────────────────────────────────────────────

const TEXTAREA_CLS =
  "flex min-h-[140px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-xs font-mono shadow-xs outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]";

function ConnectForm({ onConnected }: { onConnected: (id: string) => void }) {
  const [stableUrl, setStableUrl] = useState("");
  const [canaryUrl, setCanaryUrl] = useState("");
  const [specText, setSpecText] = useState("");
  const { mutate: create, isPending, error } = useCreateTarget();

  function submit(e: React.FormEvent) {
    e.preventDefault();
    create(
      { stable_url: stableUrl.trim(), canary_url: canaryUrl.trim(), spec_text: specText },
      { onSuccess: (data) => onConnected(data.target_id) },
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <RiPlugLine className="size-4" />
          Connect an external API pair
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Input
              placeholder="Stable base URL — https://api.example.com/v1"
              value={stableUrl}
              onChange={(e) => setStableUrl(e.target.value)}
            />
            <Input
              placeholder="Canary base URL — https://canary.example.com/v1"
              value={canaryUrl}
              onChange={(e) => setCanaryUrl(e.target.value)}
            />
          </div>
          <textarea
            className={TEXTAREA_CLS}
            placeholder="Paste OpenAPI 3.x YAML or JSON…"
            value={specText}
            onChange={(e) => setSpecText(e.target.value)}
          />
          {error && (
            <p className="text-xs text-red-500">
              {(error as Error).message}
            </p>
          )}
          <div>
            <Button type="submit" size="sm" disabled={isPending || !stableUrl || !canaryUrl || !specText}>
              <RiPlugLine className="size-3.5" />
              {isPending ? "Parsing & generating…" : "Connect & generate cases"}
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Advisory mode: GuardRail probes both versions and recommends —
            it never touches your traffic.
          </p>
        </form>
      </CardContent>
    </Card>
  );
}

// ── Target detail: cases + run + recent logs ──────────────────────────────────

function TargetDetail({ target }: { target: TargetPair }) {
  const { data: cases, isLoading: casesLoading } = useTargetCases(target.id);
  const { mutate: run, isPending: isRunning } = useTrafficRun(target.id);
  const { rows } = useLogs({ targetId: target.id, maxRows: 8 });

  const llmCount = cases?.filter((c) => c.source === "llm").length ?? 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
          <span className="font-mono text-xs">{target.id.slice(0, 8)}</span>
          <Badge variant="outline" className="text-[10px]">advisory</Badge>
          {llmCount > 0 && (
            <Badge variant="secondary" className="text-[10px]">
              {llmCount} LLM cases
            </Badge>
          )}
          <span className="ml-auto">
            <Button size="sm" onClick={() => run()} disabled={isRunning}>
              <RiPlayLine className="size-3.5" />
              {isRunning ? "Running…" : "Run probes"}
            </Button>
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 gap-2 text-xs sm:grid-cols-2">
          <p className="truncate text-muted-foreground">
            stable: <span className="font-mono text-foreground">{target.stable_url}</span>
          </p>
          <p className="truncate text-muted-foreground">
            canary: <span className="font-mono text-foreground">{target.canary_url}</span>
          </p>
        </div>
        <Separator />
        <div>
          <p className="mb-2 text-[10px] uppercase tracking-wider text-muted-foreground">
            Generated cases {cases ? `(${cases.length})` : ""}
          </p>
          {casesLoading ? (
            <Skeleton className="h-20 w-full" />
          ) : !cases?.length ? (
            <p className="text-xs text-muted-foreground">No cases yet.</p>
          ) : (
            <div className="max-h-56 space-y-1 overflow-auto">
              {cases.map((c, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <Badge variant="outline" className="font-mono text-[10px]">{c.method}</Badge>
                  <span className="truncate font-mono text-[11px]">{c.path}</span>
                  <span className="ml-auto flex shrink-0 gap-1">
                    <Badge variant="secondary" className="text-[10px]">{c.tier}</Badge>
                    <Badge variant="outline" className="text-[10px]">{c.source}</Badge>
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
        <Separator />
        <div>
          <p className="mb-2 text-[10px] uppercase tracking-wider text-muted-foreground">
            Latest target logs {rows.length > 0 ? `(${rows.length})` : ""}
          </p>
          {rows.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              Nothing yet — run probes, then open Decision &amp; Proposals with this target selected.
            </p>
          ) : (
            <div className="space-y-1">
              {rows.map((r) => (
                <div key={r.id} className="flex items-center gap-2 text-xs">
                  {r.status_code >= 500 ? (
                    <RiAlertLine className="size-3.5 shrink-0 text-red-500" />
                  ) : (
                    <RiCheckboxCircleLine className="size-3.5 shrink-0 text-emerald-500" />
                  )}
                  <span className="font-mono text-[11px]">{r.service}</span>
                  <span className="truncate font-mono text-[11px] text-muted-foreground">{r.endpoint}</span>
                  <span className="ml-auto shrink-0 font-mono text-[11px]">{r.status_code} · {r.latency_ms}ms</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ── Public view ──────────────────────────────────────────────────────────────

export function TargetsView() {
  const { data: targets, isLoading } = useTargets();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = targets?.find((t) => t.id === selectedId) ?? null;

  return (
    <div className="flex flex-col gap-6">
      <ConnectForm onConnected={setSelectedId} />
      <div>
        <p className="mb-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Connected pairs {targets ? `(${targets.length})` : ""}
        </p>
        {isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : !targets?.length ? (
          <p className="text-xs text-muted-foreground">
            No external pairs yet — connect one above to start advisory verification.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {targets.map((t) => (
              <button
                key={t.id}
                onClick={() => setSelectedId(selectedId === t.id ? null : t.id)}
                className={`rounded border p-3 text-left transition-colors hover:bg-muted/50 ${selectedId === t.id ? "border-primary" : ""}`}
              >
                <p className="font-mono text-xs">{t.id.slice(0, 8)}…</p>
                <p className="mt-1 truncate text-[11px] text-muted-foreground">{t.stable_url}</p>
                <p className="truncate text-[11px] text-muted-foreground">{t.canary_url}</p>
              </button>
            ))}
          </div>
        )}
      </div>
      {selected && <TargetDetail key={selected.id} target={selected} />}
    </div>
  );
}
