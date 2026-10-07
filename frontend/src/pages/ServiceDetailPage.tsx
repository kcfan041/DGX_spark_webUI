import { Alert, Anchor, Badge, Breadcrumbs, Card, Code, Group, SimpleGrid, Stack, Table, Tabs, Text, Title } from "@mantine/core";
import { IconRefreshDot } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useInstance, useInstanceEvents, useInstanceMetrics, useSystemInfo, useSystemSummary } from "@/api/hooks";
import type { Instance, Suggestion } from "@/api/types";
import { QueryState } from "@/components/QueryState";
import { StatusBadge } from "@/components/StatusBadge";
import { EditSettings, type EditSettingsHandle } from "@/components/service/EditSettings";
import { ErrorCard } from "@/components/service/ErrorCard";
import { EventsTimeline } from "@/components/service/EventsTimeline";
import { HowToUse } from "@/components/service/HowToUse";
import { LoadingProgress } from "@/components/service/LoadingProgress";
import { LogViewer } from "@/components/service/LogViewer";
import { ServiceActions } from "@/components/service/ServiceActions";
import { useNow } from "@/hooks/useNow";
import { useServiceActions } from "@/hooks/useServiceActions";
import { formatBytes, formatContext, formatDuration, secondsSince } from "@/lib/format";
import { isLoading } from "@/lib/status";

type Tab = "overview" | "settings" | "logs" | "events" | "diagnostics";

function GatewayCard({ instance: i }: { instance: Instance }) {
  const { t } = useTranslation();
  const color = { registered: "teal", pending: "blue", failed: "yellow", none: "gray" }[i.gateway_state];
  const msg = {
    registered: t("detail.gatewayRegistered", { name: i.served_model_name }),
    pending: t("detail.gatewayPending"),
    failed: t("detail.gatewayFailed"),
    none: t("detail.gatewayNone"),
  }[i.gateway_state];
  return (
    <Card withBorder>
      <Text fw={600} mb="xs">
        {t("detail.gateway")}
      </Text>
      <Badge color={color} variant="light" mb="xs">
        {t(`gatewayState.${i.gateway_state}`)}
      </Badge>
      <Text size="sm">{msg}</Text>
    </Card>
  );
}

function SettingsSummary({ instance: i, onEdit }: { instance: Instance; onEdit: () => void }) {
  const { t } = useTranslation();
  const p = i.params;
  return (
    <Card withBorder>
      <Group justify="space-between" mb="xs">
        <Text fw={600}>{t("detail.currentSettings")}</Text>
        <Anchor size="sm" component="button" type="button" onClick={onEdit}>
          {t("services.action.edit")}
        </Anchor>
      </Group>
      <Text size="sm">
        {[
          `${t("wizard.step.preset")}：${t(`presets.${i.preset}.label`, { defaultValue: i.preset })}`,
          `${t("params.max_model_len.label")} ${formatContext(p.max_model_len)}`,
          `${t("params.gpu_memory_utilization.label")} ${Math.round(p.gpu_memory_utilization * 100)}%`,
          `${t("params.quantization.label")} ${p.quantization === "auto" ? t("params.auto") : p.quantization}`,
          i.autostart ? t("services.autostart") : null,
        ]
          .filter(Boolean)
          .join(" · ")}
      </Text>
    </Card>
  );
}

function Diagnostics({ instance: i }: { instance: Instance }) {
  const { t } = useTranslation();
  const d = i.diagnostics;
  return (
    <Stack>
      <Table>
        <Table.Tbody>
          <Table.Tr>
            <Table.Td w={180}>{t("detail.diag.container")}</Table.Td>
            <Table.Td>
              <Code>{d?.container_name ?? "—"}</Code> {d?.container_id && <Code>{d.container_id.slice(0, 12)}</Code>}
            </Table.Td>
          </Table.Tr>
          <Table.Tr>
            <Table.Td>{t("detail.diag.image")}</Table.Td>
            <Table.Td>
              <Code style={{ wordBreak: "break-all" }}>{d?.image ?? "—"}</Code>
            </Table.Td>
          </Table.Tr>
          <Table.Tr>
            <Table.Td>{t("detail.diag.internalUrl")}</Table.Td>
            <Table.Td>
              <Code>{d?.internal_url ?? "—"}</Code>
            </Table.Td>
          </Table.Tr>
          <Table.Tr>
            <Table.Td>{t("detail.diag.gatewayId")}</Table.Td>
            <Table.Td>
              <Code>{d?.gateway_model_id ?? "—"}</Code>
            </Table.Td>
          </Table.Tr>
        </Table.Tbody>
      </Table>
      <Text fw={500}>{t("detail.diag.command")}</Text>
      <Code block>{d?.command?.join(" ") ?? "—"}</Code>
      <Text fw={500}>{t("detail.diag.raw")}</Text>
      <Code block style={{ fontSize: 11 }}>
        {JSON.stringify(i, null, 2)}
      </Code>
    </Stack>
  );
}

export function ServiceDetailPage() {
  const { t, i18n } = useTranslation();
  const { id } = useParams();
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const tab = (search.get("tab") as Tab | null) ?? "overview";
  const setTab = (v: Tab) => setSearch(v === "overview" ? {} : { tab: v }, { replace: true });
  const q = useInstance(id);
  const events = useInstanceEvents(id);
  const info = useSystemInfo();
  const summary = useSystemSummary();
  const metrics = useInstanceMetrics(id);
  const actions = useServiceActions();
  const [editInit, setEditInit] = useState<EditSettingsHandle | null>(null);
  const inst = q.data;
  const now = useNow(inst?.status === "READY");

  const onSuggestion = (s: Suggestion) => {
    if (!inst) return;
    if (s.action === "edit") {
      setEditInit({ patch: s.patch ?? undefined });
      setTab("settings");
    } else if (s.action === "apply_preset" && s.preset) {
      setEditInit({ preset: s.preset });
      setTab("settings");
    } else if (s.action === "navigate" && s.target) navigate(s.target);
    else if (s.action === "logs") setTab("logs");
    else if (s.action === "restart") actions.start(inst);
  };

  return (
    <QueryState isLoading={q.isLoading} error={q.error}>
      {!inst ? (
        <Alert color="red">{t("detail.notFound")}</Alert>
      ) : (
        <Stack>
          <Breadcrumbs>
            <Anchor component={Link} to="/services">
              {t("services.title")}
            </Anchor>
            <Text>{inst.display_name}</Text>
          </Breadcrumbs>
          <Group justify="space-between" align="flex-start">
            <Stack gap={4}>
              <Group gap="xs">
                <Title order={3}>{inst.display_name}</Title>
                {inst.autostart && (
                  <Badge variant="outline" leftSection={<IconRefreshDot size={12} />}>
                    {t("services.autostart")}
                  </Badge>
                )}
              </Group>
              <Group gap="xs">
                <StatusBadge instance={inst} />
                {inst.status === "READY" && inst.phase_started_at && (
                  <Text size="sm" c="dimmed">
                    {t("detail.uptime", { time: formatDuration(secondsSince(inst.phase_started_at, now), i18n.language) })}
                  </Text>
                )}
              </Group>
            </Stack>
            <ServiceActions
              instance={inst}
              onEdit={() => {
                setEditInit(null);
                setTab("settings");
              }}
              onLogs={() => setTab("logs")}
              onHandle={() => setTab("overview")}
            />
          </Group>

          <Tabs value={tab} onChange={(v) => v && setTab(v as Tab)} keepMounted={false}>
            <Tabs.List>
              {(["overview", "settings", "logs", "events", "diagnostics"] as Tab[]).map((k) => (
                <Tabs.Tab key={k} value={k}>
                  {t(`detail.tabs.${k}`)}
                </Tabs.Tab>
              ))}
            </Tabs.List>

            <Tabs.Panel value="overview" pt="md">
              <Stack>
                {isLoading(inst.status) && (
                  <LoadingProgress
                    instance={inst}
                    slowAfterSeconds={info.data?.timeouts?.slow_warning_s ?? 300}
                    onCancel={() => actions.cancel(inst)}
                    onViewLogs={() => setTab("logs")}
                    cancelling={actions.pendingAction === "cancel"}
                  />
                )}
                {inst.last_error && (
                  <ErrorCard error={inst.last_error} onSuggestion={onSuggestion} onViewLogs={() => setTab("logs")} />
                )}
                <HowToUse instance={inst} />
                <SimpleGrid cols={{ base: 1, md: 2 }}>
                  <GatewayCard instance={inst} />
                  <Card withBorder>
                    <Text fw={600} mb="xs">
                      {t("detail.resources")}
                    </Text>
                    <Text size="sm">
                      {t("detail.memoryQuota", {
                        ratio: Math.round(inst.params.gpu_memory_utilization * 100),
                        size: summary.data?.memory
                          ? formatBytes(inst.params.gpu_memory_utilization * summary.data.memory.total_bytes, 0)
                          : "—",
                      })}
                    </Text>
                    {metrics.data?.gpu_bytes != null && (
                      <Text size="sm" data-testid="gpu-used">
                        {t("detail.gpuUsed", { size: formatBytes(metrics.data.gpu_bytes, 1) })}
                      </Text>
                    )}
                  </Card>
                </SimpleGrid>
                <SettingsSummary
                  instance={inst}
                  onEdit={() => {
                    setEditInit(null);
                    setTab("settings");
                  }}
                />
              </Stack>
            </Tabs.Panel>

            <Tabs.Panel value="settings" pt="md">
              <EditSettings
                key={`${inst.id}-${JSON.stringify(editInit)}`}
                instance={inst}
                initial={editInit}
                onDone={() => {
                  setEditInit(null);
                  setTab("overview");
                }}
              />
            </Tabs.Panel>

            <Tabs.Panel value="logs" pt="md">
              <LogViewer instanceId={inst.id} />
            </Tabs.Panel>

            <Tabs.Panel value="events" pt="md">
              <EventsTimeline events={events.data ?? []} />
            </Tabs.Panel>

            <Tabs.Panel value="diagnostics" pt="md">
              <Diagnostics instance={inst} />
            </Tabs.Panel>
          </Tabs>
        </Stack>
      )}
    </QueryState>
  );
}
