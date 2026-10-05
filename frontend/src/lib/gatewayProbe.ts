export type ProbeResult = { ok: true; ms: number } | { ok: false; reason: "timeout" | "network" | "http"; status?: number };

export function livenessUrl(apiBase: string): string {
  const u = new URL(apiBase);
  return `${u.origin}/health/liveliness`;
}

export async function probeGateway(apiBase: string, timeoutMs = 5000): Promise<ProbeResult> {
  let url: string;
  try {
    url = livenessUrl(apiBase);
  } catch {
    return { ok: false, reason: "network" };
  }
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), timeoutMs);
  const t0 = performance.now();
  try {
    const res = await fetch(url, { signal: ctrl.signal, cache: "no-store", credentials: "omit" });
    if (!res.ok) return { ok: false, reason: "http", status: res.status };
    return { ok: true, ms: Math.round(performance.now() - t0) };
  } catch {
    return { ok: false, reason: ctrl.signal.aborted ? "timeout" : "network" };
  } finally {
    window.clearTimeout(timer);
  }
}
