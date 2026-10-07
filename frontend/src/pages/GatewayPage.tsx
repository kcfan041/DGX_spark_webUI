import { Accordion, Alert, Anchor, Badge, Button, Card, Group, Menu, Stack, Table, Text, Title } from "@mantine/core";
import { modals } from "@mantine/modals";
import { notifications } from "@mantine/notifications";
import { IconDots, IconKey, IconPlus, IconRefresh } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  useApiKeys,
  useCleanupGatewayModel,
  useConnectionInfo,
  useGatewayModels,
  useGatewayStatus,
  useResync,
  useRevokeApiKey,
  useRotateApiKey,
} from "@/api/hooks";
import type { ApiKeyInfo, CreatedApiKey } from "@/api/types";
import { EditKeyModal } from "@/components/gateway/EditKeyModal";
import { limitsSummary } from "@/lib/usage";
import { QueryState } from "@/components/QueryState";
import { CreateKeyModal } from "@/components/gateway/CreateKeyModal";
import { ApiBaseWarnings, SourceBadge } from "@/components/settings/ApiBaseCard";
import { CopyValue } from "@/components/service/HowToUse";
import { useApiErrorNotifier } from "@/hooks/useApiError";
import { formatTime } from "@/lib/format";

export function GatewayPage() {
  const { t } = useTranslation();
  const notifyError = useApiErrorNotifier();
  const status = useGatewayStatus();
  const conn = useConnectionInfo();
  const models = useGatewayModels();
  const keys = useApiKeys();
  const revoke = useRevokeApiKey();
  const resync = useResync();
  const cleanup = useCleanupGatewayModel();
  const rotate = useRotateApiKey();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<ApiKeyInfo | null>(null);
  const [rotated, setRotated] = useState<CreatedApiKey | null>(null);

  const reachable = status.data?.reachable;
  const apiBase = conn.data?.api_base ?? "";

  const confirmRevoke = (k: ApiKeyInfo) =>
    modals.openConfirmModal({
      title: t("gateway.keys.revokeTitle"),
      children: <Text size="sm">{t("gateway.keys.revokeBody", { name: k.name })}</Text>,
      labels: { confirm: t("gateway.keys.revoke"), cancel: t("common.cancel") },
      confirmProps: { color: "red" },
      onConfirm: () =>
        revoke.mutate(k.id, {
          onSuccess: () => notifications.show({ color: "teal", message: t("gateway.keys.revokedToast", { name: k.name }) }),
          onError: notifyError,
        }),
    });

  const confirmRotate = (k: ApiKeyInfo) =>
    modals.openConfirmModal({
      title: t("gateway.keys.rotateTitle"),
      children: <Text size="sm">{t("gateway.keys.rotateBody", { name: k.name })}</Text>,
      labels: { confirm: t("gateway.keys.rotate"), cancel: t("common.cancel") },
      confirmProps: { color: "orange" },
      onConfirm: () =>
        rotate.mutate(k.id, {
          onSuccess: (created) => setRotated(created),
          onError: notifyError,
        }),
    });

  const modelNames = conn.data?.models ?? [];

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={3}>{t("gateway.title")}</Title>
        {status.data && (
          <Badge color={reachable ? "teal" : "red"} variant="light" size="lg">
            {reachable ? t("dashboard.gatewayOk") : t("dashboard.gatewayDown")}
          </Badge>
        )}
      </Group>
      {status.data && !reachable && <Alert color="red">{t("errors.GATEWAY_UNREACHABLE.description")}</Alert>}

      <Card withBorder>
        <Text fw={600} mb="sm">
          {t("gateway.connection")}
        </Text>
        <Stack gap="xs">
          {apiBase && (
            <Group gap="xs">
              <CopyValue label={t("detail.apiBase")} value={apiBase} />
              {conn.data && <SourceBadge source={conn.data.source} />}
              <Anchor component={Link} to="/settings" size="sm" data-testid="api-base-edit">
                {t("apiBase.edit")}
              </Anchor>
            </Group>
          )}
          {conn.data && <ApiBaseWarnings warnings={conn.data.warnings} />}
          <Group gap={6} align="flex-start">
            <Text size="sm" c="dimmed" w={110}>
              {t("gateway.availableModels")}
            </Text>
            {(conn.data?.models ?? []).length === 0 ? (
              <Text size="sm" c="dimmed">
                {t("gateway.noModels")}
              </Text>
            ) : (
              <Stack gap={4}>
                {conn.data!.models.map((m) => (
                  <CopyValue key={m} value={m} />
                ))}
              </Stack>
            )}
          </Group>
          <Text size="sm" c="dimmed">
            {t("gateway.howTo")}
          </Text>
        </Stack>
      </Card>

      <Card withBorder>
        <Group justify="space-between" mb="sm">
          <Group gap="xs">
            <IconKey size={18} />
            <Text fw={600}>{t("gateway.keys.title")}</Text>
          </Group>
          <Button leftSection={<IconPlus size={16} />} onClick={() => setCreating(true)} disabled={!reachable} data-testid="create-key">
            {t("gateway.keys.create")}
          </Button>
        </Group>
        <Text size="sm" c="dimmed" mb="sm">
          {t("gateway.keys.intro")}
        </Text>
        <QueryState isLoading={keys.isLoading} error={keys.error} onRetry={() => keys.refetch()}>
          {(keys.data ?? []).length === 0 ? (
            <Text c="dimmed" size="sm">
              {t("gateway.keys.empty")}
            </Text>
          ) : (
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("gateway.keys.name")}</Table.Th>
                  <Table.Th>Key</Table.Th>
                  <Table.Th>{t("keyLimits.column")}</Table.Th>
                  <Table.Th>{t("gateway.keys.createdAt")}</Table.Th>
                  <Table.Th>{t("gateway.keys.status")}</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {keys.data!.map((k) => (
                  <Table.Tr key={k.id} data-testid={`key-row-${k.status}`}>
                    <Table.Td>{k.name}</Table.Td>
                    <Table.Td>
                      <Text ff="monospace" size="sm">
                        {k.masked}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <LimitsCell k={k} />
                    </Table.Td>
                    <Table.Td>{formatTime(k.created_at)}</Table.Td>
                    <Table.Td>
                      <Badge color={k.status === "active" ? "teal" : k.status === "expired" ? "orange" : "gray"} variant="light">
                        {t(`gateway.keys.${k.status}`)}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      {k.status !== "revoked" && (
                        <Menu position="bottom-end" withinPortal>
                          <Menu.Target>
                            <Button size="xs" variant="subtle" px={6} aria-label={t("common.more")} data-testid={`key-menu-${k.name}`}>
                              <IconDots size={16} />
                            </Button>
                          </Menu.Target>
                          <Menu.Dropdown>
                            <Menu.Item onClick={() => setEditing(k)} data-testid="key-edit">
                              {t("keyLimits.edit")}
                            </Menu.Item>
                            <Menu.Item onClick={() => confirmRotate(k)} data-testid="key-rotate">
                              {t("gateway.keys.rotate")}
                            </Menu.Item>
                            <Menu.Item color="red" onClick={() => confirmRevoke(k)} data-testid="key-revoke">
                              {t("gateway.keys.revoke")}
                            </Menu.Item>
                          </Menu.Dropdown>
                        </Menu>
                      )}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </QueryState>
      </Card>

      <Card withBorder>
        <Group justify="space-between" mb="sm">
          <Text fw={600}>{t("gateway.published.title")}</Text>
          <Button
            variant="default"
            size="xs"
            leftSection={<IconRefresh size={14} />}
            loading={resync.isPending}
            onClick={() =>
              resync.mutate(undefined, {
                onSuccess: () => notifications.show({ color: "teal", message: t("gateway.published.resynced") }),
                onError: notifyError,
              })
            }
          >
            {t("gateway.published.resync")}
          </Button>
        </Group>
        <QueryState isLoading={models.isLoading} error={models.error} onRetry={() => models.refetch()}>
          {(models.data ?? []).length === 0 ? (
            <Text c="dimmed" size="sm">
              {t("gateway.noModels")}
            </Text>
          ) : (
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("params.served_model_name.label")}</Table.Th>
                  <Table.Th>{t("gateway.published.service")}</Table.Th>
                  <Table.Th>{t("services.col.status")}</Table.Th>
                  <Table.Th>{t("gateway.published.sync")}</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {models.data!.map((m) => (
                  <Table.Tr key={m.gateway_model_id}>
                    <Table.Td>
                      <Text ff="monospace" size="sm">
                        {m.model_name}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      {m.instance_id ? (
                        <Anchor component={Link} to={`/services/${m.instance_id}`} size="sm">
                          {m.instance_name}
                        </Anchor>
                      ) : (
                        <Text size="sm" c="dimmed">
                          {t("gateway.published.missing")}
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>{m.instance_status ? t(`status.${m.instance_status}`) : "—"}</Table.Td>
                    <Table.Td>
                      <Badge color={m.sync === "ok" ? "teal" : "yellow"} variant="light">
                        {t(`gateway.published.${m.sync}`)}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      {m.sync === "orphan" && (
                        <Button
                          size="xs"
                          variant="subtle"
                          color="yellow"
                          loading={cleanup.isPending && cleanup.variables === m.gateway_model_id}
                          onClick={() => cleanup.mutate(m.gateway_model_id, { onError: notifyError })}
                        >
                          {t("gateway.published.cleanup")}
                        </Button>
                      )}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </QueryState>
      </Card>

      <Accordion variant="contained">
        <Accordion.Item value="adv">
          <Accordion.Control>{t("gateway.advanced")}</Accordion.Control>
          <Accordion.Panel>
            <Text size="sm">
              {t("common.labelValue", {
                label: t("gateway.dbStatus"),
                value: status.data?.db_connected ? t("dashboard.gatewayOk") : t("dashboard.gatewayDown"),
              })}
            </Text>
            <Text size="sm" c="dimmed" mt="xs">
              {t("gateway.masterKeyNote")}
            </Text>
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>

      <CreateKeyModal
        opened={creating || rotated !== null}
        onClose={() => {
          setCreating(false);
          setRotated(null);
        }}
        apiBase={apiBase}
        exampleModel={conn.data?.models[0] ?? null}
        models={modelNames}
        rotated={rotated}
      />
      <EditKeyModal apiKey={editing} onClose={() => setEditing(null)} models={modelNames} />
    </Stack>
  );
}

function LimitsCell({ k }: { k: ApiKeyInfo }) {
  const { t } = useTranslation();
  const parts = limitsSummary(k.limits, t);
  return (
    <Stack gap={2}>
      {parts.length === 0 ? (
        <Text size="sm" c="dimmed">
          {t("keyLimits.none")}
        </Text>
      ) : (
        parts.map((p) => (
          <Text size="xs" key={p}>
            {p}
          </Text>
        ))
      )}
      {k.expires_at && (
        <Text size="xs" c={k.status === "expired" ? "orange" : "dimmed"}>
          {t("keyLimits.expiresAt", { time: formatTime(k.expires_at) })}
        </Text>
      )}
      {k.spend > 0 && (
        <Text size="xs" c="dimmed">
          {t("keyLimits.spent", { amount: k.spend.toFixed(4) })}
        </Text>
      )}
    </Stack>
  );
}
