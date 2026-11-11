const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export interface Reason { code: string; text: string }
export interface CheckWindow { index: number; t_start: number; t_end: number; spoof_score: number | null }
export interface CheckResult {
  id: number; type: string; status: string; voiceprint_id: number | null;
  verdict: "green" | "yellow" | "red" | null; risk_score: number | null;
  aggregate_spoof: number | null; voiceprint_similarity: number | null;
  model_version: string | null; reasons: Reason[]; windows: CheckWindow[];
  created_at: string | null;
}
export interface Voiceprint { id: number; label: string; embedding_kind: string; sample_count: number; created_at: string | null }
export interface Circle { id: number; name: string; owner_id: number; members: { user_id: number | null; email: string | null; role: string; status: string }[] }
export interface AlertItem { id: number; check_id: number | null; message: string; read: boolean; created_at: string | null }

function token(): string | null { return localStorage.getItem("sr_token"); }
export function setToken(t: string | null) {
  if (t) localStorage.setItem("sr_token", t); else localStorage.removeItem("sr_token");
}
export function hasToken(): boolean { return !!token(); }

async function req(path: string, opts: RequestInit = {}): Promise<any> {
  const headers: Record<string, string> = { ...(opts.headers as Record<string, string> || {}) };
  const t = token();
  if (t) headers["Authorization"] = `Bearer ${t}`;
  if (opts.body && typeof opts.body === "string") headers["Content-Type"] = "application/json";
  const res = await fetch(`${BASE}${path}`, { ...opts, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  requestOtp: (email: string) => req("/auth/request-otp", { method: "POST", body: JSON.stringify({ email }) }),
  verifyOtp: (email: string, code: string, name?: string) =>
    req("/auth/verify-otp", { method: "POST", body: JSON.stringify({ email, code, name }) }),
  me: () => req("/me"),
  updateMe: (patch: { name?: string; language?: string }) =>
    req("/me", { method: "PATCH", body: JSON.stringify(patch) }),
  alerts: (): Promise<AlertItem[]> => req("/me/alerts"),
  markAlertRead: (id: number) => req(`/me/alerts/${id}/read`, { method: "POST" }),

  listVoiceprints: (): Promise<Voiceprint[]> => req("/voiceprints"),
  createVoiceprint: (label: string, blobs: Blob[]) => {
    const fd = new FormData();
    fd.append("label", label);
    blobs.forEach((b, i) => fd.append("samples", b, `sample${i + 1}.wav`));
    return req("/voiceprints", { method: "POST", body: fd });
  },
  deleteVoiceprint: (id: number) => req(`/voiceprints/${id}`, { method: "DELETE" }),

  checkClip: (audio: Blob, voiceprintId?: number | null): Promise<CheckResult> => {
    const fd = new FormData();
    fd.append("file", audio, "clip.wav");
    if (voiceprintId) fd.append("voiceprint_id", String(voiceprintId));
    return req("/checks/clip", { method: "POST", body: fd });
  },
  getCheck: (id: number): Promise<CheckResult> => req(`/checks/${id}`),
  listChecks: (): Promise<CheckResult[]> => req("/checks"),
  liveStart: (voiceprintId?: number | null) =>
    req("/checks/live/start", { method: "POST", body: JSON.stringify({ voiceprint_id: voiceprintId ?? null }) }),
  liveWindow: (checkId: number, chunk: Blob) => {
    const fd = new FormData();
    fd.append("file", chunk, "chunk.wav");
    return req(`/checks/${checkId}/windows`, { method: "POST", body: fd });
  },
  liveFinish: (checkId: number, full?: Blob | null): Promise<CheckResult> => {
    if (full) {
      const fd = new FormData();
      fd.append("file", full, "session.wav");
      return req(`/checks/${checkId}/finish`, { method: "POST", body: fd });
    }
    return req(`/checks/${checkId}/finish`, { method: "POST" });
  },
  challenge: (checkId: number, kind: string) =>
    req(`/checks/${checkId}/challenge`, { method: "POST", body: JSON.stringify({ kind }) }),
  challengeVerify: (checkId: number, passed: boolean) =>
    req(`/checks/${checkId}/challenge/verify`, { method: "POST", body: JSON.stringify({ passed }) }),

  listCircles: (): Promise<Circle[]> => req("/circles"),
  createCircle: (name: string) => req("/circles", { method: "POST", body: JSON.stringify({ name }) }),
  invite: (circleId: number, email: string) =>
    req(`/circles/${circleId}/invite`, { method: "POST", body: JSON.stringify({ email }) }),
  joinCircle: (code: string) => req("/circles/join", { method: "POST", body: JSON.stringify({ code }) }),

  report: (checkId: number | null, details: string) =>
    req("/reports", { method: "POST", body: JSON.stringify({ check_id: checkId, details }) }),
};
