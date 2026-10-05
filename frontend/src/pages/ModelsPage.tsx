import { Alert, Badge, Button, Group, Stack, Table, Text, TextInput, Title, Tooltip } from "@mantine/core";
import { IconAlertTriangle, IconRefresh, IconSearch } from "@tabler/icons-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useModelSources, useModels, useRescanModels } from "@/api/hooks";
import { QueryState } from "@/components/QueryState";
import { formatBytes, formatContext } from "@/lib/format";

export function ModelsPage() {
  const { t } = useTranslation();
  const models = useModels();
  const sources = useModelSources();
  const rescan = useRescanModels();
  const [q, setQ] = useState("");

  const rows = useMemo(
    () => (models.data ?? []).filter((m) => m.name.toLowerCase().includes(q.trim().toLowerCase())),
    [models.data, q],
  );
  const rootPath = sources.data?.find((s) => s.type === "local_dir")?.path ?? "MODEL_ROOT";

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
        </Group>
      </Group>

      <QueryState isLoading={models.isLoading} error={models.error} onRetry={() => models.refetch()}>
        {rows.length === 0 && !q ? (
          <Alert title={t("models.empty")}>{t("models.emptyHint", { path: rootPath })}</Alert>
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
                      <Badge color="green" variant="light">
                        {t("models.inUse", { count: m.in_use_by.length })}
                      </Badge>
                    ) : (
                      <Text c="dimmed" size="sm">
                        {t("models.unused")}
                      </Text>
                    )}
                  </Table.Td>
                  <Table.Td>
                    <Tooltip label={t("common.comingSoon")}>
                      <Button size="xs" disabled>
                        {t("models.createService")}
                      </Button>
                    </Tooltip>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </QueryState>
    </Stack>
  );
}
