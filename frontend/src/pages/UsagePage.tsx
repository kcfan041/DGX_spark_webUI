import {
  Badge,
  Box,
  Card,
  Group,
  Pagination,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useUsageLogs, useUsageSummary } from "@/api/hooks";
import type { UsageMetrics, UsageRow, UsageSummary } from "@/api/types";
import { QueryState } from "@/components/QueryState";
import { formatTime } from "@/lib/format";
import { fmtInt, fmtUsd, rangeDates, type UsageRange } from "@/lib/usage";

type Range = UsageRange;
type Metric = "tokens" | "requests" | "spend";

function metricValue(m: UsageMetrics, metric: Metric): number {
  return metric === "tokens" ? m.total_tokens : metric === "requests" ? m.requests : m.spend;
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card withBorder padding="sm">
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text fw={700} size="xl">
        {value}
      </Text>
      {sub && (
        <Text size="xs" c="dimmed">
          {sub}
        </Text>
      )}
    </Card>
  );
}

function DailyBars({ data, metric }: { data: UsageSummary; metric: Metric }) {
  const { t } = useTranslation();
  const values = data.days.map((d) => metricValue(d.metrics, metric));
  const at = (i: number) => values[i] ?? 0;
  const max = Math.max(...values, 0);
  const fmt = metric === "spend" ? fmtUsd : fmtInt;
  return (
    <Box>
      <Group gap={2} align="flex-end" h={120} wrap="nowrap" data-testid="usage-bars">
        {data.days.map((d, i) => (
          <Tooltip key={d.date} label={`${d.date}：${fmt(at(i))}`} withArrow>
            <Box
              style={{
                flex: 1,
                minWidth: 4,
                height: max > 0 ? `${Math.max(2, (at(i) / max) * 100)}%` : 2,
                background: at(i) > 0 ? "var(--mantine-color-blue-6)" : "var(--mantine-color-gray-3)",
                borderRadius: 2,
              }}
            />
          </Tooltip>
        ))}
      </Group>
      <Group justify="space-between" mt={4}>
        <Text size="xs" c="dimmed">
          {data.days[0]?.date}
        </Text>
        <Text size="xs" c="dimmed">
          {t("usage.peak", { value: fmt(max) })}
        </Text>
        <Text size="xs" c="dimmed">
          {data.days[data.days.length - 1]?.date}
        </Text>
      </Group>
    </Box>
  );
}

function BreakdownTable({ rows, metric, kindLabel }: { rows: UsageRow[]; metric: Metric; kindLabel: (r: UsageRow) => string }) {
  const { t } = useTranslation();
  const total = rows.reduce((a, r) => a + metricValue(r.metrics, metric), 0);
  if (rows.length === 0)
    return (
      <Text size="sm" c="dimmed">
        {t("usage.empty")}
      </Text>
    );
  return (
    <Table>
      <Table.Thead>
        <Table.Tr>
          <Table.Th>{t("usage.col.name")}</Table.Th>
          <Table.Th ta="right">{t("usage.col.requests")}</Table.Th>
          <Table.Th ta="right">{t("usage.col.input")}</Table.Th>
          <Table.Th ta="right">{t("usage.col.output")}</Table.Th>
          <Table.Th ta="right">{t("usage.col.spend")}</Table.Th>
          <Table.Th w={120}>{t("usage.col.share")}</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {rows.map((r) => {
          const share = total > 0 ? (metricValue(r.metrics, metric) / total) * 100 : 0;
          return (
            <Table.Tr key={r.id}>
              <Table.Td>
                <Text size="sm">{kindLabel(r)}</Text>
                {r.metrics.failed > 0 && (
                  <Badge size="xs" color="red" variant="light">
                    {t("usage.failed", { n: r.metrics.failed })}
                  </Badge>
                )}
              </Table.Td>
              <Table.Td ta="right">{fmtInt(r.metrics.requests)}</Table.Td>
              <Table.Td ta="right">{fmtInt(r.metrics.prompt_tokens)}</Table.Td>
              <Table.Td ta="right">{fmtInt(r.metrics.completion_tokens)}</Table.Td>
              <Table.Td ta="right">{fmtUsd(r.metrics.spend)}</Table.Td>
              <Table.Td>
                <Group gap={6} wrap="nowrap">
                  <Box h={6} w={`${Math.max(share, 1)}%`} bg="blue.5" style={{ borderRadius: 3, maxWidth: 70 }} />
                  <Text size="xs" c="dimmed">
                    {share.toFixed(0)}%
                  </Text>
                </Group>
              </Table.Td>
            </Table.Tr>
          );
        })}
      </Table.Tbody>
    </Table>
  );
}

export function UsagePage() {
  const { t } = useTranslation();
  const [range, setRange] = useState<Range>("7d");
  const [metric, setMetric] = useState<Metric>("tokens");
  const [group, setGroup] = useState<"model" | "key">("model");
  const [page, setPage] = useState(1);
  const [model, setModel] = useState<string | null>(null);
  const [status, setStatus] = useState<"success" | "failure" | null>(null);
  const { start, end } = useMemo(() => rangeDates(range), [range]);
  const summary = useUsageSummary(start, end);
  const logs = useUsageLogs({ start, end, page, model, status });
  const s = summary.data;

  const keyLabel = (r: UsageRow) =>
    r.kind === "admin"
      ? t("usage.admin")
      : r.kind === "system"
        ? t("usage.system")
        : r.kind === "revoked"
          ? `${r.label}${t("usage.revokedSuffix")}`
          : r.label || (r.kind === "unknown" ? t("usage.deletedKey") : r.id.slice(0, 8));

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={3}>{t("usage.title")}</Title>
        <SegmentedControl
          value={range}
          onChange={(v) => {
            setRange(v as Range);
            setPage(1);
          }}
          data={[
            { value: "today", label: t("usage.range.today") },
            { value: "7d", label: t("usage.range.7d") },
            { value: "30d", label: t("usage.range.30d") },
          ]}
          data-testid="usage-range"
        />
      </Group>
      <Text size="sm" c="dimmed">
        {t("usage.intro")}
      </Text>

      <QueryState isLoading={summary.isLoading} error={summary.error} onRetry={() => summary.refetch()}>
        {s && (
          <>
            <SimpleGrid cols={{ base: 2, md: 4 }} data-testid="usage-totals">
              <Stat
                label={t("usage.requests")}
                value={fmtInt(s.totals.requests)}
                sub={s.totals.failed ? t("usage.failed", { n: s.totals.failed }) : undefined}
              />
              <Stat label={t("usage.inputTokens")} value={fmtInt(s.totals.prompt_tokens)} />
              <Stat label={t("usage.outputTokens")} value={fmtInt(s.totals.completion_tokens)} />
              <Stat label={t("usage.spend")} value={fmtUsd(s.totals.spend)} sub={t("usage.spendNote")} />
            </SimpleGrid>

            <Card withBorder>
              <Group justify="space-between" mb="sm">
                <Text fw={600}>{t("usage.daily")}</Text>
                <SegmentedControl
                  size="xs"
                  value={metric}
                  onChange={(v) => setMetric(v as Metric)}
                  data={[
                    { value: "tokens", label: t("usage.metric.tokens") },
                    { value: "requests", label: t("usage.metric.requests") },
                    { value: "spend", label: t("usage.metric.spend") },
                  ]}
                />
              </Group>
              <DailyBars data={s} metric={metric} />
            </Card>

            <Card withBorder>
              <Group justify="space-between" mb="sm">
                <Text fw={600}>{t("usage.breakdown")}</Text>
                <SegmentedControl
                  size="xs"
                  value={group}
                  onChange={(v) => setGroup(v as "model" | "key")}
                  data={[
                    { value: "model", label: t("usage.byModel") },
                    { value: "key", label: t("usage.byKey") },
                  ]}
                  data-testid="usage-group"
                />
              </Group>
              {group === "model" ? (
                <BreakdownTable rows={s.by_model} metric={metric} kindLabel={(r) => r.label} />
              ) : (
                <BreakdownTable rows={s.by_key} metric={metric} kindLabel={keyLabel} />
              )}
            </Card>
          </>
        )}
      </QueryState>

      <Card withBorder>
        <Group justify="space-between" mb="sm">
          <Text fw={600}>{t("usage.recent")}</Text>
          <Group gap="xs">
            <Select
              size="xs"
              placeholder={t("usage.allModels")}
              data={(s?.by_model ?? []).map((r) => r.id)}
              value={model}
              onChange={(v) => {
                setModel(v);
                setPage(1);
              }}
              clearable
              w={200}
            />
            <Select
              size="xs"
              placeholder={t("usage.allStatus")}
              data={[
                { value: "success", label: t("usage.ok") },
                { value: "failure", label: t("usage.fail") },
              ]}
              value={status}
              onChange={(v) => {
                setStatus(v as "success" | "failure" | null);
                setPage(1);
              }}
              clearable
              w={130}
            />
          </Group>
        </Group>
        <QueryState isLoading={logs.isLoading} error={logs.error} onRetry={() => logs.refetch()}>
          {(logs.data?.items ?? []).length === 0 ? (
            <Text size="sm" c="dimmed">
              {t("usage.empty")}
            </Text>
          ) : (
            <>
              <Table.ScrollContainer minWidth={700}>
                <Table data-testid="usage-logs">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>{t("usage.col.time")}</Table.Th>
                      <Table.Th>{t("usage.col.model")}</Table.Th>
                      <Table.Th>{t("usage.col.key")}</Table.Th>
                      <Table.Th ta="right">{t("usage.col.input")}</Table.Th>
                      <Table.Th ta="right">{t("usage.col.output")}</Table.Th>
                      <Table.Th ta="right">{t("usage.col.latency")}</Table.Th>
                      <Table.Th ta="right">{t("usage.col.spend")}</Table.Th>
                      <Table.Th>{t("usage.col.status")}</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {logs.data!.items.map((r) => (
                      <Table.Tr key={r.request_id}>
                        <Table.Td>
                          <Text size="xs">{formatTime(r.time)}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="xs" ff="monospace">
                            {r.model ?? "—"}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="xs">
                            {r.key_name === "admin" ? t("usage.admin") : r.key_name === "system" ? t("usage.system") : (r.key_name ?? "—")}
                          </Text>
                        </Table.Td>
                        <Table.Td ta="right">{fmtInt(r.prompt_tokens)}</Table.Td>
                        <Table.Td ta="right">{fmtInt(r.completion_tokens)}</Table.Td>
                        <Table.Td ta="right">{r.duration_ms !== null ? `${(r.duration_ms / 1000).toFixed(1)}s` : "—"}</Table.Td>
                        <Table.Td ta="right">{fmtUsd(r.spend)}</Table.Td>
                        <Table.Td>
                          <Badge size="xs" color={r.status === "failure" ? "red" : "teal"} variant="light">
                            {r.status === "failure" ? t("usage.fail") : t("usage.ok")}
                          </Badge>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
              {logs.data!.total_pages > 1 && (
                <Group justify="center" mt="sm">
                  <Pagination total={logs.data!.total_pages} value={page} onChange={setPage} size="sm" />
                </Group>
              )}
            </>
          )}
        </QueryState>
      </Card>
    </Stack>
  );
}
