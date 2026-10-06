import { Alert, Button, Card, Code, Group, Loader, Stack, Stepper, Text } from "@mantine/core";
import { useTranslation } from "react-i18next";
import { useInstanceLogs } from "@/api/hooks";
import type { Instance, Phase } from "@/api/types";
import { useNow } from "@/hooks/useNow";
import { formatDuration, secondsSince } from "@/lib/format";

const PHASES: Phase[] = ["preparing", "creating", "loading", "registering", "ready"];

interface Props {
  instance: Instance;
  slowAfterSeconds: number;
  onCancel: () => void;
  onViewLogs: () => void;
  cancelling: boolean;
}

export function LoadingProgress({ instance, slowAfterSeconds, onCancel, onViewLogs, cancelling }: Props) {
  const { t, i18n } = useTranslation();
  const now = useNow(true);
  const logs = useInstanceLogs(instance.id, 20, 3000);
  const waited = secondsSince(instance.phase_started_at, now);
  const queued = instance.phase === "queued";
  const active = Math.max(0, PHASES.indexOf(instance.phase ?? "preparing"));
  const latest = queued ? undefined : logs.data?.lines.at(-1)?.text;

  return (
    <Card withBorder data-testid="loading-progress">
      <Stack>
        <Group justify="space-between">
          <Group gap="xs">
            <Loader size="sm" />
            <Text fw={600}>{t(queued ? "detail.queuedTitle" : "detail.loadingTitle")}</Text>
          </Group>
          <Text fw={500}>{t("detail.waited", { time: formatDuration(waited, i18n.language) })}</Text>
        </Group>
        <Stepper active={queued ? 0 : active} size="xs" allowNextStepsSelect={false}>
          {PHASES.map((p) => (
            <Stepper.Step
              key={p}
              label={t(`phase.${p}`)}
              loading={!queued && PHASES[active] === p && p !== "ready"}
            />
          ))}
        </Stepper>
        <Text size="sm" c="dimmed">
          {t(queued ? "detail.queuedHint" : "detail.loadingHint")}
        </Text>
        {!queued && waited > slowAfterSeconds && <Alert color="yellow">{t("detail.slowHint")}</Alert>}
        {latest && (
          <Stack gap={2}>
            <Text size="xs" c="dimmed">
              {t("detail.latest")}
            </Text>
            <Code style={{ whiteSpace: "pre-wrap", fontSize: 11 }}>{latest.slice(0, 300)}</Code>
          </Stack>
        )}
        <Group justify="flex-end">
          <Button variant="subtle" size="xs" onClick={onViewLogs}>
            {t("detail.viewFullLog")}
          </Button>
          <Button variant="default" size="xs" onClick={onCancel} loading={cancelling}>
            {t("services.action.cancel")}
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}
