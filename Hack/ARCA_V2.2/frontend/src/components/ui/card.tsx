import * as React from "react";
import { cn } from "@/lib/utils";

export function Card({ className, ...props }: React.ComponentProps<"div">) { return <div className={cn("rounded-2xl border border-slate-200/80 bg-white shadow-[0_8px_30px_rgba(15,23,42,0.04)]", className)} {...props} />; }
export function CardHeader({ className, ...props }: React.ComponentProps<"div">) { return <div className={cn("flex items-start justify-between gap-4 p-5 pb-0", className)} {...props} />; }
export function CardTitle({ className, ...props }: React.ComponentProps<"h2">) { return <h2 className={cn("text-base font-semibold tracking-tight text-slate-950", className)} {...props} />; }
export function CardDescription({ className, ...props }: React.ComponentProps<"p">) { return <p className={cn("mt-1 text-sm text-slate-500", className)} {...props} />; }
export function CardContent({ className, ...props }: React.ComponentProps<"div">) { return <div className={cn("p-5", className)} {...props} />; }
