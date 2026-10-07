import { Badge, Loader } from "@mantine/core";
import { useTranslation } from "react-i18next";
import type { Instance } from "@/api/types";
import { useNow } from "@/hooks/useNow";
import { formatDuration, secondsSince } from "@/lib/format";
import { STATUS_COLOR, displayStatus, isLoading } from "@/lib/status";

interface Props {
  instance: Pick<Instance, "status" | "gateway_state" | "phase_started_at" | "last_error">;
  showTimer?: boolean;
}

export function StatusBadge({ instance, showTimer = true }: Props) {
  const { t, i18n } = useTranslation();
  const ds = displayStatus(instance);
  const loading = isLoading(instance.status);
  const now = useNow(loading && showTimer);
  let label = t(`status.${ds}`);
  if (ds === "ERROR" && instance.last_error?.code) {
    label = t("common.labelValue", {
      label,
      value: t(`errors.${instance.last_error.code}.title`, { defaultValue: instance.last_error.code }),
    });
  }
  if (loading && showTimer && instance.phase_started_at) {
    label = `${label} ${formatDuration(secondsSince(instance.phase_started_at, now), i18n.language)}`;
  }
  return (
    <Badge
      color={STATUS_COLOR[ds]}
      variant="light"
      leftSection={loading ? <Loader size={10} color={STATUS_COLOR[ds]} /> : undefined}
      styles={{ label: { textTransform: "none" } }}
    >
      {label}
    </Badge>
  );
}
