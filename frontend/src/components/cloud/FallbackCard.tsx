import { Badge, Button, Card, Group, MultiSelect, NumberInput, Select, Stack, Table, Text } from "@mantine/core";
import { modals } from "@mantine/modals";
import { notifications } from "@mantine/notifications";
import { IconArrowRight, IconPlus } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useRouting, useSetFallback, useSetRetries } from "@/api/hooks";
import { QueryState } from "@/components/QueryState";
import { useApiErrorNotifier } from "@/hooks/useApiError";

export function FallbackCard({ cloudNames }: { cloudNames: string[] }) {
  const { t } = useTranslation();
  const routing = useRouting();
  const setFallback = useSetFallback();
  const setRetries = useSetRetries();
  const notifyError = useApiErrorNotifier();
  const [source, setSource] = useState<string | null>(null);
  const [targets, setTargets] = useState<string[]>([]);
  const [retries, setRetriesValue] = useState<number | string | null>(null);

  const data = routing.data;
  const models = data?.models ?? [];
  const used = new Set((data?.fallbacks ?? []).map((f) => f.model));
  const cloud = new Set(cloudNames);
  const label = (m: string) => (cloud.has(m) ? t("common.paren", { text: m, inner: t("cloud.fallback.cloudTag") }) : m);

  const save = (model: string, list: string[], done?: () => void) =>
    setFallback.mutate(
      { model, targets: list },
      {
        onSuccess: () => {
          notifications.show({ color: "teal", message: list.length ? t("cloud.fallback.saved") : t("cloud.fallback.removed") });
          done?.();
        },
        onError: notifyError,
      },
    );

  const confirmRemove = (model: string) =>
    modals.openConfirmModal({
      title: t("cloud.fallback.removeTitle"),
      children: <Text size="sm">{t("cloud.fallback.removeBody", { name: model })}</Text>,
      labels: { confirm: t("common.delete"), cancel: t("common.cancel") },
      confirmProps: { color: "red" },
      onConfirm: () => save(model, []),
    });

  return (
    <Card withBorder data-testid="fallback-card">
      <Text fw={600} mb={4}>
        {t("cloud.fallback.title")}
      </Text>
      <Text size="sm" c="dimmed" mb="sm">
        {t("cloud.fallback.intro")}
      </Text>
      <QueryState isLoading={routing.isLoading} error={routing.error} onRetry={() => routing.refetch()}>
        <Stack>
          {(data?.fallbacks ?? []).length > 0 && (
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("cloud.fallback.source")}</Table.Th>
                  <Table.Th>{t("cloud.fallback.targets")}</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {data!.fallbacks.map((f) => (
                  <Table.Tr key={f.model} data-testid={`fallback-${f.model}`}>
                    <Table.Td>
                      <Group gap={6}>
                        <Text ff="monospace" size="sm">
                          {f.model}
                        </Text>
                        {f.active_alias && (
                          <Badge size="xs" color="orange" variant="light">
                            {t("cloud.fallback.active", { target: f.active_alias })}
                          </Badge>
                        )}
                      </Group>
                    </Table.Td>
                    <Table.Td>
                      <Group gap={4}>
                        {f.targets.map((x, i) => (
                          <Group gap={4} key={x}>
                            {i > 0 && <IconArrowRight size={12} />}
                            <Badge variant="outline" tt="none">
                              {x}
                            </Badge>
                          </Group>
                        ))}
                      </Group>
                    </Table.Td>
                    <Table.Td>
                      <Button size="xs" variant="subtle" color="red" onClick={() => confirmRemove(f.model)}>
                        {t("common.delete")}
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
          {models.length < 2 ? (
            <Text size="sm" c="dimmed">
              {t("cloud.fallback.needTwo")}
            </Text>
          ) : (
            <Group align="flex-end" gap="xs" wrap="wrap">
              <Select
                label={t("cloud.fallback.source")}
                placeholder={t("cloud.fallback.pickSource")}
                data={models.filter((m) => !used.has(m)).map((m) => ({ value: m, label: label(m) }))}
                value={source}
                onChange={(v) => {
                  setSource(v);
                  setTargets([]);
                }}
                searchable
                w={240}
                data-testid="fallback-source"
              />
              <MultiSelect
                label={t("cloud.fallback.targets")}
                placeholder={t("cloud.fallback.pickTargets")}
                data={models.filter((m) => m !== source).map((m) => ({ value: m, label: label(m) }))}
                value={targets}
                onChange={setTargets}
                maxValues={5}
                disabled={!source}
                searchable
                style={{ flex: 1, minWidth: 240 }}
                data-testid="fallback-targets"
              />
              <Button
                leftSection={<IconPlus size={16} />}
                disabled={!source || targets.length === 0}
                loading={setFallback.isPending}
                onClick={() =>
                  source &&
                  save(source, targets, () => {
                    setSource(null);
                    setTargets([]);
                  })
                }
                data-testid="fallback-add"
              >
                {t("cloud.fallback.add")}
              </Button>
            </Group>
          )}
          <Text size="xs" c="dimmed">
            {t("cloud.fallback.stoppedNote")}
          </Text>
          <Group align="flex-end" gap="xs">
            <NumberInput
              label={t("cloud.fallback.retries")}
              description={t("cloud.fallback.retriesHelp")}
              min={0}
              max={5}
              allowDecimal={false}
              value={retries ?? data?.num_retries ?? 0}
              onChange={setRetriesValue}
              w={260}
            />
            <Button
              variant="default"
              disabled={retries === null || retries === "" || Number(retries) === data?.num_retries}
              loading={setRetries.isPending}
              onClick={() =>
                setRetries.mutate(Number(retries), {
                  onSuccess: () => {
                    setRetriesValue(null);
                    notifications.show({ color: "teal", message: t("cloud.fallback.retriesSaved") });
                  },
                  onError: notifyError,
                })
              }
            >
              {t("common.save")}
            </Button>
          </Group>
        </Stack>
      </QueryState>
    </Card>
  );
}
