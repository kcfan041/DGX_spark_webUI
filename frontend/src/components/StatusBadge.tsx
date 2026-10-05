import { Badge } from "@mantine/core";
import { useTranslation } from "react-i18next";
import type { InstanceStatus } from "@/api/types";

const COLORS: Record<InstanceStatus, string> = {
  CREATED: "gray",
  STOPPED: "gray",
  STARTING: "blue",
  LOADING: "blue",
  READY: "green",
  STOPPING: "gray",
  ERROR: "red",
};

export function StatusBadge({ status }: { status: InstanceStatus }) {
  const { t } = useTranslation();
  return (
    <Badge color={COLORS[status]} variant="light">
      {t(`status.${status}`)}
    </Badge>
  );
}
