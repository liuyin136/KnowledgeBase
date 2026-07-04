"use client";

import { cn } from "@/lib/utils";

export function ViewHeader({
  title,
  description,
  icon: Icon,
  actions,
  className,
}: {
  title: string;
  description?: string;
  icon?: React.ComponentType<{ className?: string }>;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 px-6 py-5 border-b bg-background/80 backdrop-blur sticky top-0 z-30", className)}>
      <div className="flex items-start gap-3 min-w-0">
        {Icon && (
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Icon className="h-5 w-5" />
          </div>
        )}
        <div className="min-w-0">
          <h1 className="text-lg font-semibold tracking-tight truncate">{title}</h1>
          {description && <p className="text-sm text-muted-foreground mt-0.5">{description}</p>}
        </div>
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
}

export function ViewBody({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("p-6 space-y-6 max-w-7xl mx-auto", className)}>{children}</div>;
}
