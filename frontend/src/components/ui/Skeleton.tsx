import React from 'react';
import { cn } from '@/lib/utils';

interface SkeletonProps { className?: string; style?: React.CSSProperties; }

export function Skeleton({ className, style }: SkeletonProps) {
  return <div className={cn('shimmer rounded-lg', className)} style={style} />;
}

export function ChartSkeleton({ height = 280 }: { height?: number }) {
  return (
    <div className="glass rounded-xl p-4 border border-white/5">
      <Skeleton className="h-4 w-32 mb-4" />
      <Skeleton style={{ height }} className="rounded-lg" />
    </div>
  );
}

export function CardSkeleton() {
  return (
    <div className="glass rounded-xl p-5 border border-white/5">
      <Skeleton className="h-8 w-8 rounded-lg mb-3" />
      <Skeleton className="h-7 w-20 mb-1" />
      <Skeleton className="h-4 w-28" />
    </div>
  );
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      <Skeleton className="h-9 w-full rounded-lg" />
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full rounded-lg" />
      ))}
    </div>
  );
}
