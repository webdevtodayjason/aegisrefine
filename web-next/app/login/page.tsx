"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { login, signup, tryUrl, ApiError } from "@/lib/api";

type Mode = "login" | "signup";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const isLogin = mode === "login";

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const fn = isLogin ? login : signup;
      const user = await fn(email.trim(), password);
      router.push(user.is_admin ? "/ops" : "/dashboard");
    } catch (ex) {
      if (ex instanceof ApiError) {
        // FastAPI errors come back as JSON {detail: "..."} or plain text.
        let msg = ex.message;
        try {
          const parsed = JSON.parse(ex.message);
          if (parsed?.detail) msg = String(parsed.detail);
        } catch {
          /* not JSON — use raw text */
        }
        setError(msg || "Something went wrong.");
      } else {
        setError("Network error — please try again.");
      }
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen md:grid-cols-[1.05fr_0.95fr]">
      <style>{`
        @keyframes ag-pulse { 0%,100% { opacity:.55 } 50% { opacity:1 } }
        @keyframes ag-float { 0%,100% { transform:translateY(0) } 50% { transform:translateY(-10px) } }
      `}</style>

      {/* LEFT: brand panel */}
      <div className="relative hidden flex-col justify-between overflow-hidden border-r border-line bg-gradient-to-b from-panel-2 to-bg px-8 py-12 md:flex lg:px-16">
        <div
          className="absolute inset-0 z-0"
          style={{
            background:
              "radial-gradient(900px 600px at 70% 30%, rgba(0,229,204,0.12), transparent 60%)",
          }}
        />

        <Link href="/" className="relative z-10 flex items-center gap-3">
          <span className="grid h-[30px] w-[30px] place-items-center rounded-md border border-teal-line bg-teal-dim text-teal shadow-[0_0_8px_rgba(0,229,204,0.4)]">
            ⛉
          </span>
          <span className="font-mono text-base font-semibold tracking-[0.16em]">
            AEGIS<span className="text-teal">&nbsp;REFINE</span>
          </span>
        </Link>

        {/* floating isometric refinement layers */}
        <div className="relative z-10 flex flex-1 items-center justify-center">
          <div style={{ perspective: "1100px", animation: "ag-float 6s ease-in-out infinite" }}>
            <div
              style={{ transformStyle: "preserve-3d", transform: "rotateX(58deg) rotateZ(45deg)" }}
              className="relative h-[190px] w-[190px]"
            >
              {[0, 46, 92].map((z, i) => (
                <div
                  key={z}
                  className="absolute inset-0 border"
                  style={{
                    transform: `translateZ(${z}px)`,
                    borderColor: `rgba(0,229,204,${0.3 + i * 0.3})`,
                    background: `rgba(0,229,204,${0.04 + i * 0.03})`,
                    backgroundImage:
                      "linear-gradient(rgba(0,229,204,.18) 1px,transparent 1px),linear-gradient(90deg,rgba(0,229,204,.18) 1px,transparent 1px)",
                    backgroundSize: "24px 24px",
                    boxShadow: `0 0 ${30 + i * 15}px rgba(0,229,204,${0.15 + i * 0.12})`,
                  }}
                >
                  {i === 2 && (
                    <div
                      className="absolute left-1/2 top-1/2 -ml-[6.5px] -mt-[6.5px] h-[13px] w-[13px] rounded-full bg-teal"
                      style={{
                        boxShadow: "0 0 22px 5px rgba(0,229,204,0.8)",
                        animation: "ag-pulse 2.2s infinite",
                      }}
                    />
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="relative z-10">
          <p className="mb-6 max-w-[420px] text-[clamp(20px,2.2vw,26px)] font-medium leading-[1.35] tracking-[-0.01em]">
            Governed autonomy for your data.{" "}
            <span className="text-teal">Real earning, gated spending, signed proof.</span>
          </p>
          <div className="flex flex-wrap gap-x-6 gap-y-2.5">
            {["HUMAN-GATED SPEND", "SIGNED AUDIT CERTS", "NVIDIA DGX SPARK"].map((f) => (
              <span
                key={f}
                className="inline-flex items-center gap-2 font-mono text-[11px] tracking-[0.08em] text-muted"
              >
                <span className="text-green">✓</span> {f}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* RIGHT: form panel */}
      <div className="flex items-center justify-center px-6 py-12 sm:px-10">
        <div className="w-full max-w-[380px]">
          <div className="mb-3.5 font-mono text-xs tracking-[0.22em] text-teal">// SECURE ACCESS</div>
          <h1 className="mb-2 text-[30px] font-medium tracking-[-0.015em]">
            {isLogin ? "Sign in to Aegis" : "Create your account"}
          </h1>
          <p className="mb-7 text-[14.5px] text-muted">
            {isLogin
              ? "Welcome back. Resume a job or start a new one."
              : "Start governed, signed, human-gated data refinement."}
          </p>

          {/* tab toggle */}
          <div className="mb-5 flex gap-1 rounded-[9px] border border-line bg-panel p-1">
            {(["login", "signup"] as Mode[]).map((m) => {
              const on = mode === m;
              return (
                <button
                  key={m}
                  type="button"
                  onClick={() => switchMode(m)}
                  className={`flex-1 rounded-md py-[9px] text-[13.5px] font-medium transition-colors ${
                    on ? "bg-teal-dim text-teal" : "text-muted hover:text-text"
                  }`}
                >
                  {m === "login" ? "Sign in" : "Create account"}
                </button>
              );
            })}
          </div>

          <form onSubmit={onSubmit} noValidate>
            <div className="mb-4">
              <label htmlFor="email" className="mb-2 block font-mono text-[10.5px] tracking-[0.12em] text-muted-2">
                EMAIL
              </label>
              <input
                id="email"
                name="email"
                type="email"
                required
                autoComplete="email"
                placeholder="you@studio.ai"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-line-2 bg-panel px-3.5 py-3 text-[14.5px] text-text outline-none transition-colors placeholder:text-muted-3 focus:border-teal-line"
              />
            </div>

            <div className="mb-2.5">
              <label htmlFor="password" className="mb-2 block font-mono text-[10.5px] tracking-[0.12em] text-muted-2">
                PASSWORD
              </label>
              <input
                id="password"
                name="password"
                type="password"
                required
                minLength={8}
                autoComplete={isLogin ? "current-password" : "new-password"}
                placeholder="••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-line-2 bg-panel px-3.5 py-3 text-[14.5px] text-text outline-none transition-colors placeholder:text-muted-3 focus:border-teal-line"
              />
              {!isLogin && (
                <div className="mt-1.5 text-[11.5px] text-muted-2">At least 8 characters.</div>
              )}
            </div>

            <button
              type="submit"
              disabled={busy}
              className="btn-teal mt-4 w-full py-3 text-[14.5px] font-semibold shadow-[0_0_24px_rgba(0,229,204,0.35)] disabled:cursor-default disabled:opacity-55"
            >
              {busy ? "Working…" : isLogin ? "Sign in →" : "Create account →"}
            </button>

            {error && (
              <div className="mt-3.5 rounded-lg border border-red/30 bg-red/[0.08] px-3 py-2.5 text-[13px] text-red">
                {error}
              </div>
            )}
          </form>

          {isLogin && (
            <p className="mt-6 text-center text-[13px] text-muted-2">
              New to Aegis?{" "}
              <button type="button" onClick={() => switchMode("signup")} className="text-teal hover:underline">
                Create an account
              </button>
            </p>
          )}

          {/* OR divider */}
          <div className="my-5 flex items-center gap-3">
            <div className="h-px flex-1 bg-white/10" />
            <span className="font-mono text-[10px] tracking-[0.14em] text-muted-3">OR</span>
            <div className="h-px flex-1 bg-white/10" />
          </div>

          <a
            href={tryUrl}
            className="flex w-full items-center justify-center gap-2.5 rounded-lg border border-teal-line bg-teal/[0.06] px-3.5 py-3 text-[14px] font-medium text-teal transition-colors hover:bg-teal-dim"
          >
            Try the demo instantly →
          </a>

          <div className="mt-5 flex items-center justify-center gap-2 font-mono text-[10px] tracking-[0.1em] text-muted-3">
            <span className="text-green">⛉</span> ENCRYPTED · POLICY-AUTH-01
          </div>
        </div>
      </div>
    </main>
  );
}
