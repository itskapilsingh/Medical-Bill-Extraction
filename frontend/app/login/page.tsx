"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { signIn, signUp } from "@/lib/auth-client";
import {
  ArrowRight,
  CheckCircle,
  Eye,
  EyeOff,
  Loader,
  ShieldCheck,
  Sparkles,
} from "@/components/icons";

type Mode = "signin" | "signup";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const isSignup = mode === "signup";

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (isSignup) {
        const { error } = await signUp.email({ email, password, name });
        if (error) throw new Error(error.message ?? "Sign up failed");
      } else {
        const { error } = await signIn.email({ email, password });
        if (error) throw new Error(error.message ?? "Sign in failed");
      }
      router.push("/dashboard");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  function switchMode() {
    setMode(isSignup ? "signin" : "signup");
    setError(null);
  }

  return (
    <main className="grid min-h-screen place-items-center bg-slate-100 p-4 sm:p-6">
      <div className="grid w-full max-w-5xl overflow-hidden rounded-3xl bg-white shadow-2xl ring-1 ring-slate-200 lg:min-h-[640px] lg:grid-cols-2">
        {/* Brand / marketing panel */}
        <aside className="relative hidden flex-col justify-between overflow-hidden bg-gradient-to-br from-[#0b2545] via-[#0a2740] to-[#0c3b39] p-10 text-white lg:flex">
          <div aria-hidden className="pointer-events-none absolute -right-24 -top-28 h-72 w-72 rounded-full bg-teal-400/20 blur-3xl" />
          <div aria-hidden className="pointer-events-none absolute -bottom-28 -left-20 h-72 w-72 rounded-full bg-indigo-500/15 blur-3xl" />

          <div className="relative inline-flex items-center gap-2 text-xs font-medium uppercase tracking-[0.18em] text-teal-300/90">
            <Sparkles className="h-4 w-4" />
            AI-powered extraction
          </div>

          <div className="relative">
            <h1 className="max-w-md text-4xl font-semibold leading-tight tracking-tight">
              From messy billing PDFs to clean, structured records.
            </h1>
            <p className="mt-4 max-w-md text-sm leading-relaxed text-slate-300">
              Upload a medical bill and the extraction agent returns itemized
              charges, payments, and adjustments — every figure traceable to its
              source page, and visible only to you.
            </p>
          </div>

          <div className="relative flex flex-wrap gap-x-5 gap-y-2 text-xs text-slate-400">
            <span className="inline-flex items-center gap-1.5">
              <ShieldCheck className="h-3.5 w-3.5 text-teal-300" /> Row-level isolation
            </span>
            <span className="inline-flex items-center gap-1.5">
              <CheckCircle className="h-3.5 w-3.5 text-teal-300" /> Source citations
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5 text-teal-300" /> Async processing
            </span>
          </div>
        </aside>

        {/* Form panel */}
        <section className="relative flex flex-col justify-center px-7 py-10 sm:px-12">
          <div className="mb-8 flex items-center justify-between">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.png" alt="Medical Bill Extraction" className="h-8 w-auto" />
            <button
              type="button"
              onClick={switchMode}
              className="text-sm font-medium text-teal-700 hover:text-teal-800"
            >
              {isSignup ? "Sign in" : "Sign up"}
            </button>
          </div>

          <div className="mx-auto w-full max-w-sm">
            <h2 className="text-2xl font-semibold tracking-tight text-slate-900">
              {isSignup ? "Create your workspace" : "Welcome back"}
            </h2>
            <p className="mt-1.5 text-sm text-slate-500">
              {isSignup
                ? "Set up an account to start extracting billing records."
                : "Sign in to upload bills and review your extractions."}
            </p>

            <form onSubmit={onSubmit} className="mt-7 space-y-4">
              {isSignup && (
                <Field label="Full name">
                  <input
                    className="input-base"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    autoComplete="name"
                    required
                  />
                </Field>
              )}

              <Field label="Email">
                <input
                  className="input-base"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  placeholder="you@example.com"
                  required
                />
              </Field>

              <Field label="Password">
                <div className="relative">
                  <input
                    className="input-base pr-10"
                    type={showPw ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete={isSignup ? "new-password" : "current-password"}
                    minLength={8}
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPw((v) => !v)}
                    className="absolute inset-y-0 right-1.5 my-auto grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:text-slate-700"
                    aria-label={showPw ? "Hide password" : "Show password"}
                    aria-pressed={showPw}
                  >
                    {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </Field>

              {error && (
                <p
                  role="alert"
                  className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
                >
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={busy}
                aria-busy={busy}
                className="btn btn-primary h-11 w-full"
              >
                {busy ? (
                  <>
                    <Loader className="h-4 w-4" />
                    <span>{isSignup ? "Creating account…" : "Signing in…"}</span>
                  </>
                ) : (
                  <>
                    {isSignup ? "Create account" : "Sign in"}
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </button>
            </form>

            <p className="mt-6 text-center text-sm text-slate-500">
              {isSignup ? "Already have an account? " : "Don't have an account? "}
              <button
                type="button"
                onClick={switchMode}
                className="font-semibold text-teal-700 hover:text-teal-800"
              >
                {isSignup ? "Sign in" : "Create one"}
              </button>
            </p>
          </div>

          <div className="mt-10 flex items-center justify-between text-xs text-slate-500">
            <span>© 2026 Medical Bill Extraction</span>
            <span className="inline-flex items-center gap-1.5">
              <ShieldCheck className="h-3.5 w-3.5" />
              Secured by per-account RLS
            </span>
          </div>
        </section>
      </div>
    </main>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-slate-600">{label}</span>
      {children}
    </label>
  );
}
