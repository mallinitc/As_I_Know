import type { LucideIcon } from "lucide-react";
import { ArrowLeft, Construction } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export function PlaceholderPage({ title, description, icon: Icon }: { title: string; description: string; icon: LucideIcon }) {
  return <div className="mx-auto flex min-h-[70vh] max-w-3xl items-center"><Card className="w-full overflow-hidden"><div className="h-1.5 bg-gradient-to-r from-blue-600 via-blue-400 to-emerald-400" /><CardContent className="flex flex-col items-center px-6 py-16 text-center"><div className="grid size-16 place-items-center rounded-2xl bg-blue-50 text-blue-700"><Icon className="size-7" /></div><Badge variant="neutral" className="mt-6"><Construction className="mr-1.5 size-3.5" /> Planned workspace</Badge><h2 className="mt-4 text-3xl font-bold tracking-tight text-[#102a43]">{title}</h2><p className="mt-3 max-w-lg text-sm leading-6 text-slate-500">{description}</p><p className="mt-2 text-xs text-slate-400">No backend connection or workflow has been invented for this migration phase.</p><Button asChild className="mt-7"><Link href="/"><ArrowLeft className="size-4" /> Return to overview</Link></Button></CardContent></Card></div>;
}
