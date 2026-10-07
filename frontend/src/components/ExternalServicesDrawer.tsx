import { Alert, Badge, Card, Code, Drawer, Group, Loader, Stack, Text } from "@mantine/core";
import { useTranslation } from "react-i18next";
import { useExternal } from "@/api/hooks";
import { formatBytes, formatTime } from "@/lib/format";

export function ExternalServicesDrawer({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const q = useExternal(opened);
  const services = q.data?.services ?? [];

  return (
    <Drawer opened={opened} onClose={onClose} title={t("external.title")} position="right" size="lg">
      <Stack>
        <Text size="sm" c="dimmed">
          {t("external.intro")}
        </Text>
        {q.isLoading && <Loader />}
        {!q.isLoading && services.length === 0 && <Alert>{t("external.none")}</Alert>}
        {q.data && q.data.total_gpu_bytes > 0 && (
          <Text size="sm">{t("external.total", { size: formatBytes(q.data.total_gpu_bytes) })}</Text>
        )}
        {services.map((s, i) => (
          <Card withBorder key={`${s.name}-${i}`} data-testid="external-item">
            <Group justify="space-between" mb={4}>
              <Group gap="xs">
                <Text fw={600} ff="monospace">
                  {s.name}
                </Text>
                <Badge size="sm" variant="light" color={s.kind === "container" ? "blue" : "gray"}>
                  {t(`external.kind.${s.kind}`)}
                </Badge>
              </Group>
              {s.gpu_bytes != null && <Badge color="yellow">{formatBytes(s.gpu_bytes)}</Badge>}
            </Group>
            <Stack gap={2}>
              {s.image && (
                <Text size="sm">
                  {t("external.image")}: <Code>{s.image}</Code>
                </Text>
              )}
              {s.status && (
                <Text size="sm">
                  {t("external.status")}: {s.status}
                  {s.started_at ? ` · ${t("external.since", { time: formatTime(s.started_at) })}` : ""}
                </Text>
              )}
              {s.ports.length > 0 && (
                <Text size="sm">
                  {t("external.ports")}: {s.ports.join(", ")}
                </Text>
              )}
              {s.compose_project && (
                <Text size="sm">
                  {t("external.compose")}: <Code>{s.compose_project}</Code>
                </Text>
              )}
              {s.pids.length > 0 && (
                <Text size="xs" c="dimmed">
                  PID {s.pids.join(", ")}
                </Text>
              )}
              <Text size="xs" c="dimmed" mt={4}>
                {t(s.hint_key, { name: s.name, project: s.compose_project ?? "" })}
              </Text>
            </Stack>
          </Card>
        ))}
      </Stack>
    </Drawer>
  );
}
