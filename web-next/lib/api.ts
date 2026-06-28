// Typed client for the Aegis FastAPI backend. Same-origin in prod (empty base); set
// NEXT_PUBLIC_API_BASE for local dev pointing at the running API.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { credentials: "include", ...init });
  if (!res.ok) throw new ApiError(res.status, await res.text().catch(() => res.statusText));
  const ct = res.headers.get("content-type") ?? "";
  return (ct.includes("application/json") ? res.json() : res.text()) as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});

// --- response shapes ---
export interface User { id: number; email: string; is_admin: boolean; }
export interface JobBrief {
  id: number; status: string; service: "refine" | "synthesis";
  quote_amount: number | null; revenue_collected: number | null; actual_cost: number | null;
  synth_topic: string | null; input: string | null; created_at: string | null;
}
export interface Quote {
  quoted_usd?: number; quote_usd?: number; cap_usd?: number; n_records?: number; data_type?: string;
  target_margin_pct: number; service?: string; mode?: string; requires_human_quote?: boolean; token?: string;
}
export interface Economics { quoted_usd: number; spent_usd: number; margin_usd: number; cap_respected: boolean; }
export interface Guarantees {
  rows: number; pii_residual: number; dupes_residual: number; schema_valid: boolean;
  synthesis?: Record<string, unknown>;
}
export interface Cert { economics?: Economics; guarantees?: Guarantees; sig?: { alg: string; value?: string }; }

// --- auth ---
export const me = () => req<User>("/auth/me");
export const login = (email: string, password: string) => req<User>("/auth/login", json({ email, password }));
export const signup = (email: string, password: string) => req<User>("/auth/signup", json({ email, password }));
export const logout = () => req<{ ok: boolean }>("/auth/logout", { method: "POST" });
export const tryUrl = `${API_BASE}/auth/try`;

// --- jobs / quotes ---
export const listJobs = () => req<JobBrief[]>("/jobs/");
export const getJob = (id: number) => req<JobBrief & { output: string | null; certificate?: { aar: string } | null }>(`/jobs/${id}`);
export const quoteRefine = (body: { dataset_url?: string; upload_handle?: string; email?: string }) =>
  req<Quote>("/jobs/quote", json(body));
export const quoteSynth = (body: { topic: string; target_kept: number; reference?: string }) =>
  req<Quote>("/jobs/synth-quote", json(body));
export const createJob = (quote_token: string) => req<{ checkout_url: string }>("/jobs/", json({ quote_token }));
export const uploadFile = (file: File) => {
  const fd = new FormData();
  fd.append("file", file);
  return req<{ handle: string; filename: string; size: number; content_type: string }>("/jobs/upload", { method: "POST", body: fd });
};
export const getCert = (id: number) => req<Cert>(`/jobs/${id}/aar`);
export const verifyJob = (id: number) =>
  req<{ ok: boolean; level: string; guarantees_recheck?: Guarantees }>(`/jobs/${id}/verify`);
export const downloadUrl = (id: number) => `${API_BASE}/jobs/${id}/download`;
export const packageUrl = (id: number) => `${API_BASE}/jobs/${id}/package`;
