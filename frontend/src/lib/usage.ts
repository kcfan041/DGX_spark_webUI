import type { KeyLimits } from "@/api/types";

export type UsageRange = "today" | "7d" | "30d";

function localDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function rangeDates(r: UsageRange, now = new Date()): { start: string; end: string } {
  const days = r === "today" ? 0 : r === "7d" ? 6 : 29;
  const s = new Date(now);
  s.setDate(s.getDate() - days);
  return { start: localDate(s), end: localDate(now) };
}

export const fmtInt = (n: number) => n.toLocaleString();
export const fmtUsd = (n: number) => (n === 0 ? "$0" : n < 0.01 ? `$${n.toFixed(4)}` : `$${n.toFixed(2)}`);

export const EMPTY_LIMITS: KeyLimits = { max_budget: null, budget_duration: null, rpm_limit: null, tpm_limit: null, models: [] };

export function limitsSummary(l: KeyLimits, t: (k: string, o?: Record<string, unknown>) => string): string[] {
  const out: string[] = [];
  if (l.models.length) out.push(t("keyLimits.sumModels", { n: l.models.length }));
  if (l.max_budget)
    out.push(
      t("keyLimits.sumBudget", {
        amount: l.max_budget,
        period: l.budget_duration ? t(`keyLimits.per${l.budget_duration}`) : "",
      }),
    );
  if (l.rpm_limit) out.push(t("keyLimits.sumRpm", { n: l.rpm_limit.toLocaleString() }));
  if (l.tpm_limit) out.push(t("keyLimits.sumTpm", { n: l.tpm_limit.toLocaleString() }));
  return out;
}
