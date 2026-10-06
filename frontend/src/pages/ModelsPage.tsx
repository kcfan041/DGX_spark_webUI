import { ActionIcon, Alert, Badge, Button, Group, Menu, Stack, Table, Text, TextInput, Title, Tooltip } from "@mantine/core";
import { modals } from "@mantine/modals";
import { notifications } from "@mantine/notifications";
import { IconAlertTriangle, IconDots, IconDownload, IconRefresh, IconSearch, IconTrash } from "@tabler/icons-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useDeleteModel, useModelSources, useModels, useRescanModels } from "@/api/hooks";
import type { ModelMeta } from "@/api/types";
import { QueryState } from "@/components/QueryState";
import { DownloadModal } from "@/components/models/DownloadModal";
import { DownloadsPanel } from "@/components/models/DownloadsPanel";
import { useApiErrorNotifier } from "@/hooks/useApiError";
import { formatBytes, formatContext } from "@/lib/format";

export function ModelsPage() {
  const { t } = useTranslation();
  const models = useModels();
  const sources = useModelSources();
  const rescan = useRescanModels();
  const del = useDeleteModel();
  const notifyError = useApiErrorNotifier();
  const [q, setQ] = useState("");
  const [downloading, setDownloading] = useState(false);

  const rows = useMemo(
    () => (models.data ?? []).filter((m) => m.name.toLowerCase().includes(q.trim().toLowerCase())),
    [models.data, q],
  );
  const rootPath = sources.data?.find((s) => s.type === "local_dir")?.path ?? "MODEL_ROOT";

  const confirmDelete = (m: ModelMeta) =>
    modals.openConfirmModal({
      title: t("models.deleteTitle"),
      children: (
        <Text size="sm">{t("models.deleteBody", { name: m.name, size: formatBytes(m.size_bytes), path: m.host_path })}</Text>
      ),
      labels: { confirm: t("common.delete"), cancel: t("common.cancel") },
      confirmProps: { color: "red" },
      onConfirm: () =>
        del.mutate(m.id, {
          onSuccess: () => notifications.show({ color: "teal", message: t("models.deleted", { name: m.name }) }),
          onError: notifyError,
        }),
    });

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={3}>{t("models.title")}</Title>
        <Group>
          <TextInput
            placeholder={t("models.search")}
            leftSection={<IconSearch size={16} />}
            value={q}
            onChange={(e) => setQ(e.currentTarget.value)}
          />
          <Button variant="default" leftSection={<IconRefresh size={16} />} loading={rescan.isPending} onClick={() => rescan.mutate()}>
            {t("models.rescan")}
          </Button>
          <Button leftSection={<IconDownload size={16} />} onClick={() => setDownloading(true)} data-testid="open-download">
            {t("downloads.open")}
          </Button>
        </Group>
      </Group>

      <DownloadsPanel />

      <QueryState isLoading={models.isLoading} error={models.error} onRetry={() => models.refetch()}>
        {rows.length === 0 && !q ? (
          <Alert title={t("models.empty")}>
            <Stack gap="xs">
              <Text size="sm">{t("models.emptyDownload")}</Text>
              <Button size="xs" w="fit-content" leftSection={<IconDownload size={14} />} onClick={() => setDownloading(true)}>
                {t("downloads.open")}
              </Button>
              <Text size="xs" c="dimmed">
                {t("models.emptyHint", { path: rootPath })}
              </Text>
            </Stack>
          </Alert>
        ) : (
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t("models.col.name")}</Table.Th>
                <Table.Th>{t("models.col.size")}</Table.Th>
                <Table.Th>{t("models.col.architecture")}</Table.Th>
                <Table.Th>{t("models.col.quantization")}</Table.Th>
                <Table.Th>{t("models.col.dtype")}</Table.Th>
                <Table.Th>{t("models.col.maxContext")}</Table.Th>
                <Table.Th>{t("models.col.usage")}</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((m) => (
                <Table.Tr key={m.id}>
                  <Table.Td>
                    <Group gap={6}>
                      <Text fw={500}>{m.name}</Text>
                      {m.needs_remote_code && (
                        <Tooltip label={t("models.remoteCode")}>
                          <IconAlertTriangle size={16} color="var(--mantine-color-yellow-6)" />
                        </Tooltip>
                      )}
                    </Group>
                  </Table.Td>
                  <Table.Td>{formatBytes(m.size_bytes)}</Table.Td>
                  <Table.Td>{m.architecture ?? t("common.unknown")}</Table.Td>
                  <Table.Td>{m.quantization ?? "—"}</Table.Td>
                  <Table.Td>{m.dtype ?? "—"}</Table.Td>
                  <Table.Td>{m.max_context ? formatContext(m.max_context) : t("common.unknown")}</Table.Td>
                  <Table.Td>
                    {m.in_use_by.length > 0 ? (
                      <Badge
                        color="green"
                        variant="light"
                        component={Link}
                        to={m.in_use_by.length === 1 ? `/services/${m.in_use_by[0]}` : "/services"}
                        style={{ cursor: "pointer" }}
                      >
                        {t("models.inUse", { count: m.in_use_by.length })}
                      </Badge>
                    ) : (
                      <Text c="dimmed" size="sm">
                        {t("models.unused")}
                      </Text>
                    )}
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4} wrap="nowrap">
                      <Button size="xs" component={Link} to={`/services/new?model=${encodeURIComponent(m.id)}`}>
                        {t("models.createService")}
                      </Button>
                      <Menu position="bottom-end" withinPortal>
                        <Menu.Target>
                          <ActionIcon variant="subtle" color="gray" aria-label="more">
                            <IconDots size={16} />
                          </ActionIcon>
                        </Menu.Target>
                        <Menu.Dropdown>
                          <Menu.Item
                            color="red"
                            leftSection={<IconTrash size={14} />}
                            disabled={m.in_use_by.length > 0 || m.source !== "local"}
                            title={
                              m.in_use_by.length > 0
                                ? t("models.deleteInUse")
                                : m.source !== "local"
                                  ? t("models.deleteNotLocal")
                                  : undefined
                            }
                            onClick={() => confirmDelete(m)}
                          >
                            {t("models.delete")}
                          </Menu.Item>
                        </Menu.Dropdown>
                      </Menu>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </QueryState>
      <DownloadModal opened={downloading} onClose={() => setDownloading(false)} />
    </Stack>
  );
}
