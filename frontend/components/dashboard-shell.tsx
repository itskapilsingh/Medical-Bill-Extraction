"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { signOut } from "@/lib/auth-client";
import { initials } from "@/lib/format";
import { CheckCircle, FileText, LayoutGrid, LogOut } from "@/components/icons";

const NAV = [
  {
    href: "/dashboard",
    label: "Documents",
    Icon: LayoutGrid,
    match: (p: string) =>
      p === "/dashboard" ||
      p.startsWith("/dashboard/documents") ||
      p.startsWith("/dashboard/jobs"),
  },
  {
    href: "/dashboard/records",
    label: "Records",
    Icon: FileText,
    match: (p: string) => p.startsWith("/dashboard/records"),
  },
];

export function DashboardShell({
  userName,
  userEmail,
  children,
}: {
  userName: string;
  userEmail: string;
  children: ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();

  async function onSignOut() {
    await signOut();
    router.push("/login");
    router.refresh();
  }

  return (
    <div className="min-h-screen">
      {/* Skip link: first focusable element, visible only on keyboard focus, so a
          keyboard/screen-reader user can jump past the header nav (WCAG 2.4.1). */}
      <a
        href="#main-content"
        className="sr-only z-50 rounded-md bg-white px-4 py-2 text-sm font-medium text-teal-700 shadow ring-2 ring-teal-500 focus:not-sr-only focus:absolute focus:left-4 focus:top-3"
      >
        Skip to main content
      </a>
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-5">
          <div className="flex min-w-0 items-center gap-5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.png" alt="Medical Bill Extraction" className="h-9 w-auto shrink-0" />
            <nav className="hidden items-center gap-1 sm:flex" aria-label="Primary">
              {NAV.map(({ href, label, Icon, match }) => {
                const active = match(pathname);
                return (
                  <Link
                    key={href}
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                      active
                        ? "bg-teal-50 text-teal-700"
                        : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    {label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden items-center gap-2.5 sm:flex">
              <div className="grid h-8 w-8 place-items-center rounded-full bg-teal-100 text-xs font-semibold text-teal-700">
                {initials(userName)}
              </div>
              <div className="leading-tight">
                <div className="text-sm font-medium text-slate-700">{userName}</div>
                <div className="text-xs text-slate-500">{userEmail}</div>
              </div>
            </div>
            <button onClick={onSignOut} aria-label="Sign out" className="btn btn-secondary btn-sm">
              <LogOut className="h-4 w-4" />
              <span className="hidden sm:inline">Sign out</span>
            </button>
          </div>
        </div>
        {/* Mobile nav row */}
        <nav className="flex items-center gap-1 border-t border-slate-100 px-5 py-1.5 sm:hidden" aria-label="Primary">
          {NAV.map(({ href, label, Icon, match }) => {
            const active = match(pathname);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                  active ? "bg-teal-50 text-teal-700" : "text-slate-600 hover:bg-slate-50"
                }`}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>
      </header>

      <main
        id="main-content"
        tabIndex={-1}
        className="mx-auto max-w-6xl space-y-6 px-5 py-8 focus:outline-none"
      >
        {children}
      </main>

      <footer className="flex items-center justify-center gap-1.5 px-5 pb-8 text-xs text-slate-500">
        <CheckCircle className="h-3.5 w-3.5" />
        Per-account isolation enforced at the database (RLS)
      </footer>
    </div>
  );
}
