import { Skeleton } from "@/components/ui/skeleton";

export function DashboardSkeleton() {
  return <div className="space-y-6" aria-label="Loading dashboard"><div className="space-y-3"><Skeleton className="h-6 w-36" /><Skeleton className="h-10 w-[min(520px,85%)]" /><Skeleton className="h-5 w-[min(680px,95%)]" /></div><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-44 rounded-2xl" />)}</div><div className="grid gap-6 xl:grid-cols-[0.85fr_1.4fr]"><Skeleton className="h-[340px] rounded-2xl" /><Skeleton className="h-[340px] rounded-2xl" /></div><Skeleton className="h-64 rounded-2xl" /></div>;
}
