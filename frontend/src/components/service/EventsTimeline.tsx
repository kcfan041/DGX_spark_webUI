import { Text, Timeline } from "@mantine/core";
import { useTranslation } from "react-i18next";
import type { InstanceEvent } from "@/api/types";
import { formatTime } from "@/lib/format";

const COLOR: Record<string, string> = {
  error: "red",
  gateway_failed: "yellow",
  test_failed: "yellow",
  autostart_error: "red",
  gateway_registered: "teal",
  model_loaded: "teal",
  test_ok: "teal",
  autostart_ready: "teal",
};

export function EventsTimeline({ events }: { events: InstanceEvent[] }) {
  const { t } = useTranslation();
  if (events.length === 0) return <Text c="dimmed">{t("detail.noEvents")}</Text>;
  return (
    <Timeline bulletSize={14} lineWidth={2}>
      {events.map((e) => {
        const params: Record<string, unknown> = { ...e.data };
        if (typeof e.data.code === "string") params.code = t(`errors.${e.data.code}.title`, { defaultValue: e.data.code });
        const reason = typeof e.data.reason === "string" ? t(`events.reason.${e.data.reason}`, { defaultValue: e.data.reason }) : null;
        return (
          <Timeline.Item key={e.id} color={COLOR[e.type] ?? "gray"} title={t(`events.${e.type}`, { ...params, defaultValue: e.type })}>
            <Text size="xs" c="dimmed">
              {formatTime(e.created_at)}
              {reason ? ` · ${reason}` : ""}
            </Text>
          </Timeline.Item>
        );
      })}
    </Timeline>
  );
}
