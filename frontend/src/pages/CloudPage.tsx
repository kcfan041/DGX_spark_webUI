import { Alert, Badge, Button, Card, Group, Menu, Stack, Table, Text, Title } from "@mantine/core";
import { modals } from "@mantine/modals";
import { notifications } from "@mantine/notifications";
import { IconCloud, IconDots, IconPlus } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useCloudModels, useDeleteCloudModel, useDeleteProvider, useGatewayStatus, useProviders } from "@/api/hooks";
import type { CloudModel, CloudProvider } from "@/api/types";
import { QueryState } from "@/components/QueryState";
import { AddModelModal } from "@/components/cloud/AddModelModal";
import { FallbackCard } from "@/components/cloud/FallbackCard";
import { ProviderModal } from "@/components/cloud/ProviderModal";
import { useApiErrorNotifier } from "@/hooks/useApiError";

const price = (v: number | null) => (v === null ? "—" : `$${v}`);

export function CloudPage() {
  const { t } = useTranslation();
  const notifyError = useApiErrorNotifier();
  const status = useGatewayStatus();
  const providers = useProviders();
  const models = useCloudModels();
  const delProvider = useDeleteProvider();
  const delModel = useDeleteCloudModel();
  const [providerModal, setProviderModal] = useState<{ open: boolean; editing: CloudProvider | null }>({ open: false, editing: null });
  const [addModel, setAddModel] = useState<{ open: boolean; provider: string | null }>({ open: false, provider: null });
  const reachable = status.data?.reachable !== false;
  const list = providers.data ?? [];

  const confirmDeleteProvider = (p: CloudProvider) =>
    modals.openConfirmModal({
      title: t("cloud.provider.deleteTitle"),
      children: <Text size="sm">{t("cloud.provider.deleteBody", { name: p.name, n: p.models })}</Text>,
      labels: { confirm: t("common.delete"), cancel: t("common.cancel") },
      confirmProps: { color: "red" },
      onConfirm: () =>
        delProvider.mutate(p.id, {
          onSuccess: () => notifications.show({ color: "teal", message: t("cloud.provider.deleted", { name: p.name }) }),
          onError: notifyError,
        }),
    });

  const confirmDeleteModel = (m: CloudModel) =>
    modals.openConfirmModal({
      title: t("cloud.model.deleteTitle"),
      children: <Text size="sm">{t("cloud.model.deleteBody", { name: m.name })}</Text>,
      labels: { confirm: t("common.delete"), cancel: t("common.cancel") },
      confirmProps: { color: "red" },
      onConfirm: () =>
        delModel.mutate(m.id, {
          onSuccess: () => notifications.show({ color: "teal", message: t("cloud.model.deleted", { name: m.name }) }),
          onError: notifyError,
        }),
    });

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={3}>{t("cloud.title")}</Title>
      </Group>
      <Text size="sm" c="dimmed">
        {t("cloud.intro")}
      </Text>
      {!reachable && <Alert color="red">{t("errors.GATEWAY_UNREACHABLE.description")}</Alert>}

      <Card withBorder>
        <Group justify="space-between" mb="sm">
          <Group gap="xs">
            <IconCloud size={18} />
            <Text fw={600}>{t("cloud.provider.title")}</Text>
          </Group>
          <Button
            leftSection={<IconPlus size={16} />}
            onClick={() => setProviderModal({ open: true, editing: null })}
            disabled={!reachable}
            data-testid="add-provider"
          >
            {t("cloud.provider.add")}
          </Button>
        </Group>
        <QueryState isLoading={providers.isLoading} error={providers.error} onRetry={() => providers.refetch()}>
          {list.length === 0 ? (
            <Text size="sm" c="dimmed">
              {t("cloud.provider.empty")}
            </Text>
          ) : (
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("cloud.provider.name")}</Table.Th>
                  <Table.Th>{t("cloud.provider.type")}</Table.Th>
                  <Table.Th>{t("cloud.provider.apiKey")}</Table.Th>
                  <Table.Th>{t("cloud.provider.models")}</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {list.map((p) => (
                  <Table.Tr key={p.id} data-testid={`provider-row-${p.name}`}>
                    <Table.Td>
                      <Text size="sm">{p.name}</Text>
                      {p.api_base && (
                        <Text size="xs" c="dimmed" ff="monospace">
                          {p.api_base}
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Badge variant="light">{t(`cloud.types.${p.type}`)}</Badge>
                    </Table.Td>
                    <Table.Td>
                      <Text ff="monospace" size="sm">
                        {p.masked_key ?? "—"}
                      </Text>
                    </Table.Td>
                    <Table.Td>{p.models}</Table.Td>
                    <Table.Td>
                      <Group gap={4} justify="flex-end" wrap="nowrap">
                        <Button size="xs" variant="light" onClick={() => setAddModel({ open: true, provider: p.id })}>
                          {t("cloud.model.add")}
                        </Button>
                        <Menu position="bottom-end" withinPortal>
                          <Menu.Target>
                            <Button size="xs" variant="subtle" px={6} aria-label={t("common.more")}>
                              <IconDots size={16} />
                            </Button>
                          </Menu.Target>
                          <Menu.Dropdown>
                            <Menu.Item onClick={() => setProviderModal({ open: true, editing: p })}>{t("cloud.provider.edit")}</Menu.Item>
                            <Menu.Item color="red" onClick={() => confirmDeleteProvider(p)}>
                              {t("common.delete")}
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
      </Card>

      <Card withBorder>
        <Group justify="space-between" mb="sm">
          <Text fw={600}>{t("cloud.model.title")}</Text>
          <Button
            variant="light"
            leftSection={<IconPlus size={16} />}
            disabled={list.length === 0 || !reachable}
            onClick={() => setAddModel({ open: true, provider: null })}
            data-testid="add-cloud-model"
          >
            {t("cloud.model.add")}
          </Button>
        </Group>
        <Text size="sm" c="dimmed" mb="sm">
          {t("cloud.model.intro")}
        </Text>
        <QueryState isLoading={models.isLoading} error={models.error} onRetry={() => models.refetch()}>
          {(models.data ?? []).length === 0 ? (
            <Text size="sm" c="dimmed">
              {list.length === 0 ? t("cloud.model.emptyNoProvider") : t("cloud.model.empty")}
            </Text>
          ) : (
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("cloud.model.name")}</Table.Th>
                  <Table.Th>{t("cloud.model.model")}</Table.Th>
                  <Table.Th>{t("cloud.model.provider")}</Table.Th>
                  <Table.Th>{t("cloud.model.price")}</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {models.data!.map((m) => (
                  <Table.Tr key={m.id} data-testid={`cloud-model-${m.name}`}>
                    <Table.Td>
                      <Text ff="monospace" size="sm">
                        {m.name}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" c="dimmed">
                        {m.model}
                      </Text>
                    </Table.Td>
                    <Table.Td>{m.provider_name ?? <Text c="red" size="sm">{t("cloud.model.providerMissing")}</Text>}</Table.Td>
                    <Table.Td>
                      <Text size="xs">
                        {t("cloud.model.priceValue", { input: price(m.input_per_mtok), output: price(m.output_per_mtok) })}
                      </Text>
                      {m.custom_price && (
                        <Badge size="xs" variant="light" color="grape">
                          {t("cloud.model.customPriceTag")}
                        </Badge>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Button size="xs" variant="subtle" color="red" onClick={() => confirmDeleteModel(m)}>
                        {t("common.delete")}
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </QueryState>
      </Card>

      <FallbackCard cloudNames={(models.data ?? []).map((m) => m.name)} />

      <ProviderModal
        opened={providerModal.open}
        editing={providerModal.editing}
        onClose={() => setProviderModal({ open: false, editing: null })}
        onCreated={(p) => {
          notifications.show({ color: "teal", message: t("cloud.provider.created", { name: p.name }) });
          setAddModel({ open: true, provider: p.id });
        }}
      />
      <AddModelModal
        opened={addModel.open}
        onClose={() => setAddModel({ open: false, provider: null })}
        providers={list}
        initialProvider={addModel.provider}
      />
    </Stack>
  );
}
