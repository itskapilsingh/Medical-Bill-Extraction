"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { signIn, signUp } from "@/lib/auth-client";
import { Loader, Logo } from "@/components/icons";

type Mode = "signin" | "signup";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "signup") {
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

  const tab = (m: Mode, label: string) => (
    <button
      type="button"
      onClick={() => {
        setMode(m);
        setError(null);
      }}
      className={`flex-1 rounded-md py-1.5 text-sm font-medium transition ${
        mode === m
          ? "bg-white text-slate-900 shadow-sm ring-1 ring-slate-200"
          : "text-slate-500 hover:text-slate-700"
      }`}
    >
      {label}
    </button>
  );

  const field = (
    label: string,
    value: string,
    set: (v: string) => void,
    type: string,
    autoComplete: string,
    extra: Record<string, unknown> = {},
  ) => (
    <div>
      <label className="mb-1 block text-xs font-medium text-slate-600">{label}</label>
      <input
        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm shadow-sm outline-none transition placeholder:text-slate-400 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
        type={type}
        value={value}
        onChange={(e) => set(e.target.value)}
        autoComplete={autoComplete}
        required
        {...extra}
      />
    </div>
  );

  return (
    <main className="relative grid min-h-screen place-items-center overflow-hidden px-4">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(60rem_40rem_at_50%_-10%,#e0e7ff_0%,transparent_60%)]"
      />
      <div className="w-full max-w-sm">
        <div className="mb-7 flex flex-col items-center text-center">
          <Logo className="mb-4 h-12 w-12" />
          <h1 className="text-lg font-semibold tracking-tight text-slate-900">
            Medical Billing Extraction
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Upload billing PDFs and review extracted records — scoped to your account.
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="mb-5 flex gap-1 rounded-lg bg-slate-100 p-1">
            {tab("signin", "Sign in")}
            {tab("signup", "Create account")}
          </div>

          <form onSubmit={onSubmit} className="space-y-3.5">
            {mode === "signup" &&
              field("Full name", name, setName, "text", "name")}
            {field("Email", email, setEmail, "email", "email")}
            {field(
              "Password",
              password,
              setPassword,
              "password",
              mode === "signup" ? "new-password" : "current-password",
              { minLength: 8 },
            )}

            {error && (
              <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={busy}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy && <Loader className="h-4 w-4" />}
              {busy ? "Please wait…" : mode === "signup" ? "Create account" : "Sign in"}
            </button>
          </form>
        </div>

        <p className="mt-5 text-center text-xs text-slate-400">
          Secured by per-account row-level isolation.
        </p>
      </div>
    </main>
  );
}
