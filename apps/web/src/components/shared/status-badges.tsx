import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface VerdictBadgeProps {
  verdict: string;
  className?: string;
}

const verdictStyles: Record<string, string> = {
  keep: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20 dark:text-emerald-400",
  escalate: "bg-red-500/10 text-red-600 border-red-500/20 dark:text-red-400",
};

const verdictLabels: Record<string, string> = {
  keep: "Keep Canary",
  escalate: "Escalate",
};

export function VerdictBadge({ verdict, className }: VerdictBadgeProps) {
  return (
    <Badge
      variant="outline"
      className={cn(verdictStyles[verdict] ?? "", className)}
    >
      {verdictLabels[verdict] ?? verdict}
    </Badge>
  );
}

interface StatusBadgeProps {
  status: number;
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const isError = status >= 500;
  const isClientError = status >= 400 && status < 500;
  return (
    <Badge
      variant="outline"
      className={cn(
        isError
          ? "bg-red-500/10 text-red-600 border-red-500/20 dark:text-red-400"
          : isClientError
            ? "bg-amber-500/10 text-amber-600 border-amber-500/20 dark:text-amber-400"
            : "bg-emerald-500/10 text-emerald-600 border-emerald-500/20 dark:text-emerald-400",
        className,
      )}
    >
      {status}
    </Badge>
  );
}

interface ServiceBadgeProps {
  service: string;
  className?: string;
}

export function ServiceBadge({ service, className }: ServiceBadgeProps) {
  const isStable = service === "stable";
  const isCanary = service === "canary";
  const isProxy = service.startsWith("proxy");
  return (
    <Badge
      variant="outline"
      className={cn(
        isStable
          ? "bg-blue-500/10 text-blue-600 border-blue-500/20 dark:text-blue-400"
          : isCanary
            ? "bg-violet-500/10 text-violet-600 border-violet-500/20 dark:text-violet-400"
            : isProxy
              ? "bg-amber-500/10 text-amber-600 border-amber-500/20 dark:text-amber-400"
              : "",
        className,
      )}
    >
      {service}
    </Badge>
  );
}
