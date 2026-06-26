import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";
import { DashboardShell } from "@/components/dashboard-shell";
import { RecordsClient } from "./records-client";

export const dynamic = "force-dynamic";

export default async function RecordsPage() {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/login");

  return (
    <DashboardShell
      userName={session.user.name ?? session.user.email}
      userEmail={session.user.email}
    >
      <RecordsClient />
    </DashboardShell>
  );
}
