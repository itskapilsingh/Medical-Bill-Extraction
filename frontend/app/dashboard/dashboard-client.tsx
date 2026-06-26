"use client";

import { useMemo, useRef, useState } from "react";
import Link from "next/link";

import { ApiError, uploadPdfs } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { uploadErrorMessage } from "@/lib/messages";
import { useToast } from "@/components/toast";
import { useJobs, useSummary } from "@/lib/use-jobs";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle,
  FileText,
  Inbox,
  LayoutGrid,
  Loader,
  RefreshCw,
  UploadCloud,
  X,
} from "@/components/icons";
import { JobCard } from "./job-card";

const RECENT_LIMIT = 5;

export default function DashboardClient() {
  const toast = useToast();
  const { jobs, loading, loadError, refresh, onCancel, handleAuthExpiry } = useJobs();
  const { summary, refreshSummary } = useSummary();
  const [uploading, setUploading] = useState(false);
  const [bypassCache, setBypassCache] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // Headline numbers come from the server-side aggregate, so they're correct no
  // matter how many documents the user has (the recents list below is just a peek).
  const cards = {
    total: summary?.total ?? 0,
    completed: summary?.completed ?? 0,
    records: summary?.records_count ?? 0,
    flagged: summary?.flagged_count ?? 0,
  };

  const recent = jobs.slice(0, RECENT_LIMIT);
  const isProcessing = (summary?.processing ?? 0) > 0;

  async function refreshAll() {
    await Promise.all([refresh(), refreshSummary()]);
  }
  const uploadButtonLabel =
    files.length === 0
      ? "Upload & extract"
      : `Upload ${files.length} PDF${files.length === 1 ? "" : "s"} & extract`;

  const selectedBytes = useMemo(
    () => files.reduce((total, selected) => total + selected.size, 0),
    [files],
  );

  function isPdf(f: File): boolean {
    return f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf");
  }

  function pickFiles(selected: FileList | File[] | null) {
    const picked = selected ? Array.from(selected) : [];
    const pdfs = picked.filter(isPdf);
    if (picked.length > pdfs.length) {
      toast.error("Only PDF files can be uploaded.");
    }
    setFiles(pdfs);
  }

  function clearFiles() {
    setFiles([]);
    if (fileRef.current) fileRef.current.value = "";
  }

  function removeFile(index: number) {
    setFiles((current) => current.filter((_, i) => i !== index));
    if (fileRef.current) fileRef.current.value = "";
  }

  async function onUpload(e: React.FormEvent) {
    e.preventDefault();
    if (files.length === 0) return;
    setUploading(true);
    try {
      const result = await uploadPdfs(files, bypassCache);
      const authFailure = result.failed.find(
        ({ error }) => error instanceof ApiError && error.status === 401,
      );
      if (authFailure && handleAuthExpiry(authFailure.error)) return;

      if (result.accepted.length > 0) {
        await refreshAll();
      }

      if (result.failed.length === 0) {
        clearFiles();
        toast.success(
          `${result.accepted.length} PDF${result.accepted.length === 1 ? "" : "s"} accepted. Extracting records...`,
        );
        return;
      }

      setFiles(result.failed.map(({ file }) => file));
      if (fileRef.current) fileRef.current.value = "";

      if (result.accepted.length > 0) {
        toast.success(
          `${result.accepted.length} PDF${result.accepted.length === 1 ? "" : "s"} accepted.`,
        );
      }
      const firstFailure = result.failed[0];
      toast.error(
        `${result.failed.length} upload${
          result.failed.length === 1 ? "" : "s"
        } failed. ${firstFailure.file.name}: ${uploadErrorMessage(firstFailure.error)}`,
      );
    } catch (err) {
      if (handleAuthExpiry(err)) return;
      toast.error(uploadErrorMessage(err));
    } finally {
      setUploading(false);
    }
  }

  return (
    <>
      <h1 className="sr-only">Dashboard</h1>
      {/* Stats */}
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard
          label="Documents"
          value={cards.total}
          accent="slate"
          Icon={FileText}
          href="/dashboard/documents"
        />
        <StatCard
          label="Completed"
          value={cards.completed}
          accent="emerald"
          Icon={CheckCircle}
          href="/dashboard/documents"
        />
        <StatCard
          label="Records extracted"
          value={cards.records}
          accent="teal"
          Icon={LayoutGrid}
          href="/dashboard/records"
        />
        <StatCard
          label="Needs review"
          value={cards.flagged}
          accent="amber"
          Icon={AlertTriangle}
          href="/dashboard/records"
        />
      </section>

      {/* Upload */}
      <section className="card p-5">
        <h2 className="text-sm font-semibold text-slate-900">Upload billing PDFs</h2>
        <p className="mt-0.5 text-sm text-slate-500">
          Processed asynchronously by the extraction agent. Results are visible only to
          your account.
        </p>

        <form onSubmit={onUpload} className="mt-4 space-y-3">
          <label
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              pickFiles(e.dataTransfer.files ?? null);
            }}
            className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-center transition focus-within:border-teal-500 focus-within:ring-2 focus-within:ring-teal-500/30 ${
              dragging
                ? "border-teal-400 bg-teal-50"
                : "border-slate-300 bg-slate-50 hover:border-slate-400 hover:bg-slate-100/60"
            }`}
          >
            <input
              ref={fileRef}
              type="file"
              accept="application/pdf,.pdf"
              multiple
              className="sr-only"
              onChange={(e) => pickFiles(e.target.files)}
            />
            {files.length > 0 ? (
              <div className="flex max-w-full flex-wrap items-center justify-center gap-2.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-sm">
                <FileText className="h-4 w-4 text-teal-600" />
                <span className="font-medium text-slate-800">
                  {files.length} PDF{files.length === 1 ? "" : "s"} selected
                </span>
                <span className="text-slate-500">{formatBytes(selectedBytes)}</span>
              </div>
            ) : (
              <>
                <UploadCloud className="h-7 w-7 text-slate-400" />
                <div className="text-sm text-slate-600">
                  <span className="font-medium text-teal-700">Click to browse</span> or drag
                  &amp; drop PDFs
                </div>
              </>
            )}
          </label>

          {files.length > 0 && (
            <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
              <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-3 py-2">
                <div className="min-w-0 text-xs font-medium text-slate-500">
                  {files.length} selected ({formatBytes(selectedBytes)})
                </div>
                <button
                  type="button"
                  onClick={clearFiles}
                  className="rounded-md px-2 py-1 text-xs font-medium text-slate-500 transition hover:bg-slate-100 hover:text-slate-800"
                >
                  Clear
                </button>
              </div>
              <ul className="scrollbar-thin max-h-40 divide-y divide-slate-100 overflow-y-auto">
                {files.map((selected, index) => (
                  <li
                    key={`${selected.name}-${selected.size}-${selected.lastModified}-${index}`}
                    className="flex items-center gap-2 px-3 py-2 text-sm"
                  >
                    <FileText className="h-4 w-4 shrink-0 text-teal-600" />
                    <span className="min-w-0 flex-1 truncate font-medium text-slate-700">
                      {selected.name}
                    </span>
                    <span className="shrink-0 text-xs text-slate-500">
                      {formatBytes(selected.size)}
                    </span>
                    <button
                      type="button"
                      onClick={() => removeFile(index)}
                      aria-label={`Remove ${selected.name}`}
                      title={`Remove ${selected.name}`}
                      className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <label
              className="inline-flex cursor-pointer items-center gap-2 text-sm text-slate-600"
              title="Always run a fresh extraction even if this file was processed before"
            >
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
                checked={bypassCache}
                onChange={(e) => setBypassCache(e.target.checked)}
              />
              Bypass cache
            </label>
            <button type="submit" disabled={uploading || files.length === 0} className="btn btn-primary">
              {uploading ? <Loader className="h-4 w-4" /> : <UploadCloud className="h-4 w-4" />}
              {uploading ? "Uploading..." : uploadButtonLabel}
            </button>
          </div>
        </form>
      </section>

      {/* Recent documents (a short preview — the full, filterable list is /dashboard/documents) */}
      <section>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-slate-900">Recent documents</h2>
          <div className="flex items-center gap-3">
            {isProcessing && (
              <span className="inline-flex items-center gap-1.5 text-xs font-medium text-blue-600">
                <Loader className="h-3.5 w-3.5" />
                processing…
              </span>
            )}
            <button onClick={() => void refreshAll()} className="btn btn-secondary btn-sm">
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </button>
          </div>
        </div>

        <p className="sr-only" role="status" aria-live="polite">
          {loading
            ? "Loading documents."
            : `${cards.total} document${cards.total === 1 ? "" : "s"}, ${summary?.processing ?? 0} processing, ${cards.flagged} needing review.`}
        </p>

        {loadError && (
          <p
            role="alert"
            className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
          >
            {loadError}
          </p>
        )}

        {loading ? (
          <div className="space-y-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="skeleton h-16 rounded-xl" />
            ))}
          </div>
        ) : jobs.length === 0 ? (
          <div className="grid place-items-center rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-14 text-center">
            <span className="mb-3 grid h-12 w-12 place-items-center rounded-full bg-slate-100 text-slate-400">
              <Inbox className="h-6 w-6" />
            </span>
            <div className="text-sm font-medium text-slate-700">No documents yet</div>
            <div className="mt-1 text-sm text-slate-500">
              Upload a billing PDF above to extract its records.
            </div>
          </div>
        ) : (
          <>
            <ul className="space-y-2.5">
              {recent.map((job) => (
                <JobCard key={job.job_id} job={job} onCancel={onCancel} />
              ))}
            </ul>
            {cards.total > recent.length && (
              <Link
                href="/dashboard/documents"
                className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-teal-700 transition hover:gap-2.5 hover:text-teal-800"
              >
                View all {cards.total} documents
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            )}
          </>
        )}
      </section>
    </>
  );
}

const STAT_TONES: Record<string, { value: string; chip: string }> = {
  slate: { value: "text-slate-900", chip: "bg-slate-100 text-slate-600" },
  emerald: { value: "text-emerald-600", chip: "bg-emerald-50 text-emerald-600" },
  teal: { value: "text-teal-600", chip: "bg-teal-50 text-teal-600" },
  amber: { value: "text-amber-600", chip: "bg-amber-50 text-amber-600" },
};

function StatCard({
  label,
  value,
  accent = "slate",
  href,
  Icon,
}: {
  label: string;
  value: number;
  accent?: "slate" | "emerald" | "teal" | "amber";
  href?: string;
  Icon: (p: { className?: string }) => React.ReactElement;
}) {
  const tone = STAT_TONES[accent];
  const body = (
    <div className="flex items-center gap-3">
      <span
        className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg ${tone.chip}`}
      >
        <Icon className="h-4 w-4" />
      </span>
      <div className="min-w-0">
        <div className="truncate text-xs font-medium text-slate-500">{label}</div>
        <div className={`text-xl font-semibold tabular-nums ${tone.value}`}>
          {value.toLocaleString()}
        </div>
      </div>
    </div>
  );
  if (href) {
    return (
      <Link href={href} className="card-link block px-4 py-3.5">
        {body}
      </Link>
    );
  }
  return <div className="card px-4 py-3.5">{body}</div>;
}
