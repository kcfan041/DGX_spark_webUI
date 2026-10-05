import { Alert, Badge, Button, Group, Stack, Table, Text, Title, Tooltip } from "@mantine/core";
import { IconPlus, IconRefreshDot } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useInstances } from "@/api/hooks";
import { QueryState } from "@/components/QueryState";
import { StatusBadge } from "@/components/StatusBadge";

export function ServicesPage() {
  const { t } = useTranslation();
  const instances = useInstances();
  const rows = instances.data ?? [];

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={3}>{t("services.title")}</Title>
        <Tooltip label={t("common.comingSoon")}>
          <Button leftSection={<IconPlus size={16} />} disabled>
            {t("services.create")}
          </Button>
        </Tooltip>
      </Group>
      <QueryState isLoading={instances.isLoading} error={instances.error} onRetry={() => instances.refetch()}>
        {rows.length === 0 ? (
          <Alert title={t("services.empty")}>
            <Stack gap="xs">
              <Text size="sm">{t("services.intro")}</Text>
              <Button component={Link} to="/models" size="xs" variant="light" w="fit-content">
                {t("services.fromModel")}
              </Button>
            </Stack>
          </Alert>
        ) : (
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t("services.col.name")}</Table.Th>
                <Table.Th>{t("services.col.model")}</Table.Th>
                <Table.Th>{t("services.col.status")}</Table.Th>
                <Table.Th>{t("services.col.gateway")}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((i) => (
                <Table.Tr key={i.id}>
                  <Table.Td>
                    <Group gap={6}>
                      {i.display_name}
                      {i.autostart && (
                        <Badge size="xs" variant="outline" leftSection={<IconRefreshDot size={10} />}>
                          {t("services.autostart")}
                        </Badge>
                      )}
                    </Group>
                  </Table.Td>
                  <Table.Td>{i.model_id}</Table.Td>
                  <Table.Td>
                    <StatusBadge status={i.status} />
                  </Table.Td>
                  <Table.Td>{i.gateway_state}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </QueryState>
    </Stack>
  );
}
