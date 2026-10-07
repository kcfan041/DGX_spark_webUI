import { ActionIcon, Badge, Button, Card, Group, Progress, Stack, Text, Tooltip } from "@mantine/core";
import { modals } from "@mantine/modals";
import { IconPlayerStop, IconRefresh, IconX } from "@tabler/icons-react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { notifications } from "@mantine/notifications";
import { useDownloadAction, useDownloads } from "@/api/hooks";
import type { DownloadInfo, DownloadStatus } from "@/api/types";
import { useApiErrorNotifier } from "@/hooks/useApiError";
import { formatBytes, formatDuration } from "@/lib/format";

const COLOR: Record<DownloadStatus, string> = {
  queued: "gray",
  downloading: "blue",
  completed: "teal",
  failed: "red",
  cancelled: "gray",
};

const STALL_AFTER_S = 30;

function eta(d: DownloadInfo): number | null {
  if (!d.speed_bps || !d.bytes_total || d.speed_bps < 1) return null;
  return Math.max(0, (d.bytes_total - d.bytes_done) / d.speed_bps);
}

function ProgressLine({ d }: { d: DownloadInfo }) {
  const { t, i18n } = useTranslation();
  if (d.status === "queued")
    return (
      <Text size="xs" c="dimmed">
        {t("downloads.queuedHint")}
      </Text>
    );
  const pct = d.progress != null ? Math.round(d.progress * 100) : 0;
  const sizes = t("downloads.sizeLine", { done: formatBytes(d.bytes_done), total: formatBytes(d.bytes_total), pct });
  const stalled = (d.stalled_s ?? 0) >= STALL_AFTER_S;
  const left = eta(d);
  let rate: string;
  if (stalled) rate = t("downloads.stalled", { time: formatDuration(d.stalled_s ?? 0, i18n.language) });
  else if (d.speed_bps == null || (d.speed_bps < 1 && left == null)) rate = t("downloads.measuring");
  else
    rate = t("downloads.rateLine", {
      speed: `${formatBytes(d.speed_bps)}/s`,
      eta: left != null ? formatDuration(left, i18n.language) : t("downloads.measuring"),
    });
  return (
    <Text size="xs" c={stalled ? "orange" : "dimmed"} data-testid="download-progress">
      {sizes} · {rate}
    </Text>
  );
}

export function DownloadsPanel() {
  const { t } = useTranslation();
  const q = useDownloads();
  const qc = useQueryClient();
  const action = useDownloadAction();
  const notifyError = useApiErrorNotifier();
  const prev = useRef<Map<string, DownloadStatus> | null>(null);

  useEffect(() => {
    if (!q.data) return;
    const now = new Map(q.data.map((d) => [d.id, d.status]));
    if (prev.current) {
      for (const d of q.data) {
        const before = prev.current.get(d.id);
        if (before && before !== d.status && d.status === "completed") {
          notifications.show({ color: "teal", message: t("downloads.done", { repo: d.repo_id }) });
          void qc.invalidateQueries({ queryKey: ["models"] });
          void qc.invalidateQueries({ queryKey: ["model-sources"] });
        }
        if (before && before !== d.status && d.status === "failed")
          notifications.show({ color: "red", message: t("downloads.failedToast", { repo: d.repo_id }) });
      }
    }
    prev.current = now;
  }, [q.data, t, qc]);

  const items = (q.data ?? []).filter(
    (d) => d.status !== "completed" || Date.now() - Date.parse(d.finished_at ?? d.created_at) < 24 * 3600 * 1000,
  );
  if (items.length === 0) return null;

  const run = (id: string, a: "cancel" | "retry" | "delete") =>
    action.mutate({ id, action: a }, { onError: notifyError });

  return (
    <Card withBorder data-testid="downloads-panel">
      <Text fw={600} mb="xs">
        {t("downloads.panel")}
      </Text>
      <Stack gap="sm">
        {items.map((d) => {
          const pct = d.progress != null ? Math.round(d.progress * 100) : null;
          return (
            <Stack key={d.id} gap={4} data-testid={`download-${d.status}`}>
              <Group justify="space-between" wrap="nowrap">
                <Group gap="xs" wrap="nowrap">
                  <Text size="sm" fw={500} ff="monospace">
                    {d.repo_id}
                  </Text>
                  <Badge size="sm" variant="light" color={COLOR[d.status]}>
                    {t(`downloads.status.${d.status}`)}
                  </Badge>
                </Group>
                <Group gap={4} wrap="nowrap">
                  {d.status === "completed" && d.model_id && (
                    <Button
                      size="compact-xs"
                      component={Link}
                      to={`/services/new?model=${encodeURIComponent(d.model_id)}`}
                    >
                      {t("models.createService")}
                    </Button>
                  )}
                  {(d.status === "failed" || d.status === "cancelled") && (
                    <Tooltip label={t("downloads.retry")}>
                      <ActionIcon variant="subtle" onClick={() => run(d.id, "retry")} aria-label="retry">
                        <IconRefresh size={16} />
                      </ActionIcon>
                    </Tooltip>
                  )}
                  {(d.status === "queued" || d.status === "downloading") && (
                    <Tooltip label={t("downloads.cancel")}>
                      <ActionIcon
                        variant="subtle"
                        color="red"
                        aria-label="cancel"
                        data-testid="download-cancel"
                        onClick={() =>
                          modals.openConfirmModal({
                            title: t("downloads.cancelTitle"),
                            children: <Text size="sm">{t("downloads.cancelBody", { repo: d.repo_id })}</Text>,
                            labels: { confirm: t("common.confirm"), cancel: t("common.cancel") },
                            confirmProps: { color: "red" },
                            onConfirm: () => run(d.id, "cancel"),
                          })
                        }
                      >
                        <IconPlayerStop size={16} />
                      </ActionIcon>
                    </Tooltip>
                  )}
                  {d.status !== "queued" && d.status !== "downloading" && (
                    <Tooltip label={t("downloads.dismiss")}>
                      <ActionIcon
                        variant="subtle"
                        color="gray"
                        onClick={() => run(d.id, "delete")}
                        aria-label="dismiss"
                      >
                        <IconX size={16} />
                      </ActionIcon>
                    </Tooltip>
                  )}
                </Group>
              </Group>
              {(d.status === "downloading" || d.status === "queued") && (
                <>
                  <Progress value={pct ?? 0} animated={d.status === "downloading"} striped />
                  <ProgressLine d={d} />
                </>
              )}
              {d.status === "failed" && d.error && (
                <Text size="xs" c="red">
                  {t(`downloads.errors.${d.error.code}`, { defaultValue: d.error.message ?? d.error.code })}
                </Text>
              )}
              {d.status === "completed" && (
                <Text size="xs" c="dimmed">
                  {t("downloads.savedTo", { dir: d.target_dir, size: formatBytes(d.bytes_total) })}
                </Text>
              )}
              {d.error?.leftover && (
                <Text size="xs" c="orange" data-testid="download-leftover">
                  {t("downloads.leftover", { path: d.error.leftover })}
                </Text>
              )}
            </Stack>
          );
        })}
      </Stack>
    </Card>
  );
}
