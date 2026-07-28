export type JobStatus = {
  run_id: string;
  owner_email?: string;
  query: string;
  country: string;
  profile: string;
  cap: string;
  running: boolean;
  cancelled: boolean;
  cancel_requested?: boolean;
  cancel_requested_at?: number | null;
  error?: string | null;
  status: string;
  started_at: number;
  elapsed_seconds: number;
  phase: number;
  phase_label: string;
  progress_pct: number;
  log_tail: string;
  has_result: boolean;
  slug: string;
  companies: number;
  csv_path?: string | null;
  xlsx_path?: string | null;
  docx_path?: string | null;
};

export type Me = {
  email: string;
  role: string;
  user_id: number;
  expires_at: string;
};

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
    if (Array.isArray(data?.detail)) {
      return data.detail.map((d: { msg?: string }) => d.msg || JSON.stringify(d)).join("; ");
    }
    return JSON.stringify(data);
  } catch {
    return res.statusText || `HTTP ${res.status}`;
  }
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers || {});
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(path, {
    ...init,
    headers,
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(await parseError(res));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}
