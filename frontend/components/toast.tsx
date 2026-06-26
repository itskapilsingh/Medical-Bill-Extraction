"use client";

// Lightweight, accessible toast notifications — no external dependency, in the
// same hand-rolled style as the rest of the UI. Success/info toasts are announced
// politely; errors assertively (role="alert"). Each toast auto-dismisses and can
// be dismissed manually. Mount <ToastProvider> once near the root; call useToast()
// from any client component to raise one.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";

import { CheckCircle, Info, X, XCircle } from "@/components/icons";

type ToastVariant = "success" | "error" | "info";

interface ToastOptions {
  /** Override the auto-dismiss delay in ms. Pass 0 to make the toast sticky. */
  duration?: number;
}

interface ToastRecord {
  id: number;
  message: string;
  variant: ToastVariant;
  duration?: number;
}

interface ToastApi {
  success: (message: string, opts?: ToastOptions) => void;
  error: (message: string, opts?: ToastOptions) => void;
  info: (message: string, opts?: ToastOptions) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

/** Access the toast API. Must be called from under a <ToastProvider>. */
export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within a <ToastProvider>");
  return ctx;
}

// Errors linger longest so they aren't missed; success is brief.
const DEFAULT_DURATION: Record<ToastVariant, number> = {
  success: 4000,
  info: 5000,
  error: 8000,
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastRecord[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (variant: ToastVariant, message: string, opts?: ToastOptions) => {
      const id = nextId.current++;
      setToasts((prev) => [...prev, { id, message, variant, duration: opts?.duration }]);
    },
    [],
  );

  const api = useMemo<ToastApi>(
    () => ({
      success: (m, o) => push("success", m, o),
      error: (m, o) => push("error", m, o),
      info: (m, o) => push("info", m, o),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

const VARIANTS: Record<
  ToastVariant,
  { Icon: (p: { className?: string }) => ReactElement; ring: string; icon: string }
> = {
  success: { Icon: CheckCircle, ring: "ring-emerald-200", icon: "text-emerald-600" },
  error: { Icon: XCircle, ring: "ring-red-200", icon: "text-red-600" },
  info: { Icon: Info, ring: "ring-slate-200", icon: "text-slate-500" },
};

function ToastViewport({
  toasts,
  onDismiss,
}: {
  toasts: ToastRecord[];
  onDismiss: (id: number) => void;
}) {
  // pointer-events-none on the wrapper so it never blocks the page; each toast
  // re-enables pointer events for its dismiss button.
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 p-4 sm:items-end">
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

function ToastItem({
  toast,
  onDismiss,
}: {
  toast: ToastRecord;
  onDismiss: (id: number) => void;
}) {
  useEffect(() => {
    const ms = toast.duration ?? DEFAULT_DURATION[toast.variant];
    if (ms <= 0) return; // sticky — caller asked for no auto-dismiss
    const timer = setTimeout(() => onDismiss(toast.id), ms);
    return () => clearTimeout(timer);
  }, [toast, onDismiss]);

  const { Icon, ring, icon } = VARIANTS[toast.variant];
  const isError = toast.variant === "error";

  return (
    <div
      role={isError ? "alert" : "status"}
      aria-live={isError ? "assertive" : "polite"}
      className={`toast-enter pointer-events-auto flex w-full max-w-sm items-start gap-2.5 rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-sm text-slate-800 shadow-lg ring-1 ${ring}`}
    >
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${icon}`} />
      <span className="min-w-0 flex-1 break-words">{toast.message}</span>
      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss notification"
        className="-mr-1 -mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-md text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
