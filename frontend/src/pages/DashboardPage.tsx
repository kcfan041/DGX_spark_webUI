import { Alert, Anchor, Badge, Button, Card, Group, Progress, SimpleGrid, Stack, Table, Text, Title } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useInstances, useSystemSummary } from "@/api/hooks";
import type { InstanceStatus } from "@/api/types";
import { QueryState } from "@/components/QueryState";
import { StatusBadge } from "@/components/StatusBadge";
import { formatBytes, percent } from "@/lib/format";

const COUNT_ORDER: { label: InstanceStatus; include: InstanceStatus[]; color: string }[] = [
  { label: "READY", include: ["READY"], color: "green" },
  { label: "LOADING", include: ["STARTING", "LOADING"], color: "blue" },
  { label: "ERROR", include: ["ERROR"], color: "red" },
  { label: "STOPPED", include: ["STOPPED", "CREATED"], color: "gray" },
];

export function DashboardPage() {
  const { t } = useTranslation();
  const summary = useSystemSummary();
  const instances = useInstances();
  const s = summary.data;
  const running = (instances.data ?? []).filter((i) => !["STOPPED", "CREATED"].includes(i.status));

  return (
    <QueryState isLoading={summary.isLoading} error={summary.error} onRetry={() => summary.refetch()}>
      {s && (
        <Stack>
          <Title order={3}>{t(`health.${s.health}`)}</Title>

          {s.external_services > 0 && (
            <Alert color="yellow" icon={<IconAlertTriangle />}>
              {t("dashboard.externalServices", { count: s.external_services })}
            </Alert>
          )}

          <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
            <Card withBorder>
              <Text fw={600}>{t("dashboard.spark")}</Text>
              <Badge color={s.capabilities.docker ? "green" : "red"} variant="light" mt="xs">
                {t(s.capabilities.docker ? "dashboard.gatewayOk" : "dashboard.gatewayDown")}
              </Badge>
              {s.gpu?.utilization_pct != null && (
                <Text size="sm" c="dimmed" mt="xs">
                  {t("dashboard.gpuUtil", { pct: s.gpu.utilization_pct })}
                </Text>
              )}
            </Card>

            {s.memory && (
              <Card withBorder>
                <Text fw={600}>{t("dashboard.memory")}</Text>
                <Progress value={percent(s.memory.used_bytes, s.memory.total_bytes)} mt="xs" />
                <Text size="sm" mt={4}>
                  {formatBytes(s.memory.used_bytes)} / {formatBytes(s.memory.total_bytes)}
                </Text>
                <Text size="xs" c="dimmed">
                  {t("dashboard.memoryShared")} · {t("dashboard.memoryCached", { size: formatBytes(s.memory.cached_bytes) })}
                </Text>
              </Card>
            )}

            {s.disk && (
              <Card withBorder>
                <Text fw={600}>{t("dashboard.disk")}</Text>
                <Progress value={percent(s.disk.used_bytes, s.disk.total_bytes)} mt="xs" />
                <Text size="sm" mt={4}>
                  {formatBytes(s.disk.used_bytes)} / {formatBytes(s.disk.total_bytes)}
                </Text>
                <Text size="xs" c="dimmed">
                  {t("dashboard.diskModels")}
                </Text>
              </Card>
            )}

            <Card withBorder>
              <Text fw={600}>{t("dashboard.gateway")}</Text>
              <Badge color={s.gateway.reachable ? "green" : "red"} variant="light" mt="xs">
                {t(s.gateway.reachable ? "dashboard.gatewayOk" : "dashboard.gatewayDown")}
              </Badge>
            </Card>
          </SimpleGrid>

          <Group>
            {COUNT_ORDER.map(({ label, include, color }) => (
              <Badge key={label} color={color} variant="dot" size="lg">
                {t(`status.${label}`)} {include.reduce((n, k) => n + (s.counts[k] ?? 0), 0)}
              </Badge>
            ))}
          </Group>

          <Card withBorder>
            <Text fw={600} mb="sm">
              {t("dashboard.runningServices")}
            </Text>
            {running.length === 0 ? (
              <Group>
                <Text c="dimmed">{t("dashboard.noRunning")}</Text>
                <Button component={Link} to="/models" variant="light" size="xs">
                  {t("dashboard.goModels")}
                </Button>
              </Group>
            ) : (
              <Table>
                <Table.Tbody>
                  {running.map((i) => (
                    <Table.Tr key={i.id}>
                      <Table.Td>
                        <Anchor component={Link} to={`/services/${i.id}`}>
                          {i.display_name}
                        </Anchor>
                      </Table.Td>
                      <Table.Td>
                        <StatusBadge status={i.status} />
                      </Table.Td>
                      <Table.Td>{i.served_model_name}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </Card>

          <Card withBorder>
            <Text fw={600} mb="sm">
              {t("dashboard.howToConnect")}
            </Text>
            <Anchor component={Link} to="/gateway">
              {t("dashboard.needKey")}
            </Anchor>
          </Card>
        </Stack>
      )}
    </QueryState>
  );
}
