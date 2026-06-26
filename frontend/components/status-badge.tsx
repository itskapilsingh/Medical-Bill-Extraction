import type { JobStatus } from "@/lib/types";
import { CheckCircle, Clock, Loader, XCircle } from "@/components/icons";

type Meta = {
  label: string;
  cls: string;
  Icon: (p: { className?: string }) => React.ReactElement;
};

export const STATUS: Record<JobStatus, Meta> = {
  completed: { label: "Completed", cls: "bg-emerald-50 text-emerald-700 ring-emerald-200", Icon: CheckCircle },
  processing: { label: "Processing", cls: "bg-blue-50 text-blue-700 ring-blue-200", Icon: Loader },
  pending: { label: "Pending", cls: "bg-slate-100 text-slate-600 ring-slate-200", Icon: Clock },
  failed: { label: "Failed", cls: "bg-red-50 text-red-700 ring-red-200", Icon: XCircle },
  cancelled: { label: "Cancelled", cls: "bg-zinc-100 text-zinc-600 ring-zinc-200", Icon: XCircle },
};

export function StatusBadge({ status }: { status: JobStatus }) {
  const { label, cls, Icon } = STATUS[status];
  return (
    <span className={`badge ring-1 ring-inset ${cls}`}>
      <Icon className="h-3.5 w-3.5" />
      {label}
    </span>
  );
}
