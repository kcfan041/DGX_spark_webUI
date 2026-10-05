import { Accordion, Alert, Card, Code, Group, Progress, Stack, Text, Tooltip } from "@mantine/core";
import { IconAlertTriangle, IconBan, IconInfoCircle } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import type { Plan, PlanWarning, WarningLevel } from "@/api/types";
import { formatBytes, formatContext } from "@/lib/format";

const LEVEL_COLOR: Record<WarningLevel, string> = { info: "gray", warning: "yellow", blocking: "red" };
const LEVEL_ICON = { info: IconInfoCircle, warning: IconAlertTriangle, blocking: IconBan };
const ORDER: WarningLevel[] = ["blocking", "warning", "info"];

function fmtParam(v: unknown): string {
  if (typeof v === "number") {
    if (v > 10_000_000) return formatBytes(v);
    if (v > 0 && v < 1) return `${Math.round(v * 100)}%`;
    return String(v);
  }
  if (Array.isArray(v)) return v.join(", ");
  return String(v ?? "");
}

export function WarningList({ warnings }: { warnings: PlanWarning[] }) {
  const { t } = useTranslation();
  if (warnings.length === 0) return null;
  const sorted = [...warnings].sort((a, b) => ORDER.indexOf(a.level) - ORDER.indexOf(b.level));
  return (
    <Stack gap="xs">
      {sorted.map((w, i) => {
        const Icon = LEVEL_ICON[w.level];
        const params = Object.fromEntries(Object.entries(w.params).map(([k, v]) => [k, fmtParam(v)]));
        return (
          <Alert key={`${w.code}-${i}`} color={LEVEL_COLOR[w.level]} icon={<Icon size={16} />} p="xs" data-level={w.level}>
            <Text size="sm">
              <b>{t(`warnings.level.${w.level}`)}</b>{"　"}{t(`warnings.${w.code}`, { ...params, defaultValue: w.code })}
            </Text>
          </Alert>
        );
      })}
    </Stack>
  );
}

export function MemoryEstimateCard({ plan }: { plan: Plan }) {
  const { t } = useTranslation();
  const e = plan.estimate;
  const total = e.total_bytes ?? 0;
  const scale = Math.max(total, e.budget_bytes ?? 0, 1);
  const pct = (v: number | null) => ((v ?? 0) / scale) * 100;
  return (
    <Card withBorder>
      <Group justify="space-between" mb="xs">
        <Text fw={600}>{t("estimate.title")}</Text>
        <Text size="xs" c="dimmed">
          {t("estimate.disclaimer")}
        </Text>
      </Group>
      <Progress.Root size={22}>
        <Tooltip label={`${t("estimate.weights")} ${formatBytes(e.weights_bytes)}`}>
          <Progress.Section value={pct(e.weights_bytes)} color="teal">
            <Progress.Label>{t("estimate.weights")}</Progress.Label>
          </Progress.Section>
        </Tooltip>
        <Tooltip label={`${t("estimate.kv")} ${formatBytes(e.kv_cache_bytes)}`}>
          <Progress.Section value={pct(e.kv_cache_bytes)} color="cyan">
            <Progress.Label>{t("estimate.kv")}</Progress.Label>
          </Progress.Section>
        </Tooltip>
        <Tooltip label={`${t("estimate.overhead")} ${formatBytes(e.overhead_bytes)}`}>
          <Progress.Section value={pct(e.overhead_bytes)} color="gray">
            <Progress.Label>{t("estimate.overhead")}</Progress.Label>
          </Progress.Section>
        </Tooltip>
      </Progress.Root>
      <Stack gap={2} mt="xs">
        <Text size="sm">
          {t("estimate.weights")} {formatBytes(e.weights_bytes)} · {t("estimate.kv")} ~{formatBytes(e.kv_cache_bytes)} ·{" "}
          {t("estimate.overhead")} ~{formatBytes(e.overhead_bytes)} · {t("estimate.total")} {formatBytes(e.total_bytes)}
        </Text>
        {e.budget_bytes != null && (
          <Text size="sm">
            {t("estimate.budget", {
              ratio: Math.round(plan.params.gpu_memory_utilization * 100),
              size: formatBytes(e.budget_bytes),
            })}
          </Text>
        )}
        {e.system_available_bytes != null && (
          <Text size="sm" c="dimmed">
            {t("estimate.available", {
              size: formatBytes(e.system_available_bytes),
              free: formatBytes(e.system_free_bytes),
            })}
          </Text>
        )}
      </Stack>
    </Card>
  );
}

export function PlanSummary({ plan, modelName }: { plan: Plan; modelName: string }) {
  const { t } = useTranslation();
  const p = plan.params;
  return (
    <Stack>
      <MemoryEstimateCard plan={plan} />
      <WarningList warnings={plan.warnings} />
      <Card withBorder>
        <Text fw={600} mb="xs">
          {t("wizard.finalSettings")}
        </Text>
        <Text size="sm">
          {[
            `${t("services.col.model")} ${modelName}`,
            `${t("params.served_model_name.label")} ${plan.served_model_name}`,
            `${t("params.max_model_len.label")} ${formatContext(p.max_model_len)}`,
            `${t("params.gpu_memory_utilization.label")} ${Math.round(p.gpu_memory_utilization * 100)}%`,
            `${t("params.quantization.label")} ${p.quantization === "auto" ? t("params.auto") : p.quantization}`,
            plan.autostart ? t("services.autostart") : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        </Text>
      </Card>
      <Accordion variant="contained">
        <Accordion.Item value="cmd">
          <Accordion.Control>{t("wizard.showCommand")}</Accordion.Control>
          <Accordion.Panel>
            <Code block>{plan.command.join(" ")}</Code>
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
    </Stack>
  );
}
