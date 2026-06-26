import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";
import { DashboardShell } from "@/components/dashboard-shell";
import { JobDetailClient } from "./job-detail-client";

export const dynamic = "force-dynamic";

export default async function JobReportPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/login");
  const { id } = await params;

  return (
    <DashboardShell
      userName={session.user.name ?? session.user.email}
      userEmail={session.user.email}
    >
      <JobDetailClient jobId={id} />
    </DashboardShell>
  );
}
