import { Alert, Anchor, Badge, Button, Group, SegmentedControl, Stack, Table, Text, Title } from "@mantine/core";
import { IconPlus, IconRefreshDot } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useInstances, useModels } from "@/api/hooks";
import { QueryState } from "@/components/QueryState";
import { StatusBadge } from "@/components/StatusBadge";
import { ServiceActions } from "@/components/service/ServiceActions";
import { STATUS_GROUPS, type StatusGroup } from "@/lib/status";

export function ServicesPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const instances = useInstances();
  const models = useModels();
  const all = instances.data ?? [];
  const group = (search.get("status") as StatusGroup | null) ?? "all";
  const allowed = STATUS_GROUPS[group] as readonly string[] | null | undefined;
  const rows = allowed ? all.filter((i) => allowed.includes(i.status)) : all;
  const count = (g: StatusGroup) => {
    const s = STATUS_GROUPS[g] as readonly string[] | null;
    return s ? all.filter((i) => s.includes(i.status)).length : all.length;
  };
  const modelName = (id: string) => models.data?.find((m) => m.id === id)?.name ?? id;

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={3}>{t("services.title")}</Title>
        <Button leftSection={<IconPlus size={16} />} component={Link} to="/services/new">
          {t("services.create")}
        </Button>
      </Group>
      <SegmentedControl
        w="fit-content"
        value={group}
        onChange={(v) => setSearch(v === "all" ? {} : { status: v }, { replace: true })}
        data={(Object.keys(STATUS_GROUPS) as StatusGroup[]).map((g) => ({
          value: g,
          label: `${t(`services.filter.${g}`)} ${count(g)}`,
        }))}
      />
      <QueryState isLoading={instances.isLoading} error={instances.error} onRetry={() => instances.refetch()}>
        {all.length === 0 ? (
          <Alert title={t("services.empty")}>
            <Stack gap="xs">
              <Text size="sm">{t("services.intro")}</Text>
              <Button component={Link} to="/models" size="xs" variant="light" w="fit-content">
                {t("services.fromModel")}
              </Button>
            </Stack>
          </Alert>
        ) : (
          <Table highlightOnHover verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t("services.col.name")}</Table.Th>
                <Table.Th>{t("services.col.model")}</Table.Th>
                <Table.Th>{t("services.col.status")}</Table.Th>
                <Table.Th>{t("services.col.gateway")}</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((i) => (
                <Table.Tr key={i.id}>
                  <Table.Td>
                    <Group gap={6}>
                      <Anchor component={Link} to={`/services/${i.id}`} fw={500}>
                        {i.display_name}
                      </Anchor>
                      {i.autostart && (
                        <Badge size="xs" variant="outline" leftSection={<IconRefreshDot size={10} />}>
                          {t("services.autostart")}
                        </Badge>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">
                      {i.served_model_name}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{modelName(i.model_id)}</Text>
                  </Table.Td>
                  <Table.Td>
                    <StatusBadge instance={i} />
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c={i.gateway_state === "registered" ? "teal" : "dimmed"}>
                      {i.gateway_state === "registered" ? "✓ " : "— "}
                      {t(`gatewayState.${i.gateway_state}`)}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <ServiceActions
                      compact
                      instance={i}
                      onEdit={() => navigate(`/services/${i.id}?tab=settings`)}
                      onLogs={() => navigate(`/services/${i.id}?tab=logs`)}
                      onHandle={() => navigate(`/services/${i.id}`)}
                    />
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
