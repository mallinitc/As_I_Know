import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold", { variants: { variant: {
  default: "border-blue-200 bg-blue-50 text-blue-700", success: "border-emerald-200 bg-emerald-50 text-emerald-700",
  warning: "border-amber-200 bg-amber-50 text-amber-700", destructive: "border-red-200 bg-red-50 text-red-700", danger: "border-red-200 bg-red-50 text-red-700", neutral: "border-slate-200 bg-slate-50 text-slate-600",
}}, defaultVariants: { variant: "default" }});
export function Badge({ className, variant, ...props }: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) { return <span className={cn(badgeVariants({ variant }), className)} {...props} />; }
