"use client";

import { RiRefreshLine } from "@remixicon/react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface RefreshButtonProps {
  onClick: () => void;
  loading?: boolean;
  className?: string;
  label?: string;
}

export function RefreshButton({
  onClick,
  loading = false,
  className,
  label = "Refresh",
}: RefreshButtonProps) {
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={onClick}
      disabled={loading}
      className={className}
    >
      <RiRefreshLine className={cn("size-3.5", loading && "animate-spin")} />
      {label}
    </Button>
  );
}
