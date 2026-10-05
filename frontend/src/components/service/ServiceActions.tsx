import { ActionIcon, Button, Group, Menu } from "@mantine/core";
import { IconDots, IconPlayerPlay, IconPlayerStop, IconRefresh, IconTrash } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import type { Instance } from "@/api/types";
import { useServiceActions } from "@/hooks/useServiceActions";
import { isLoading, isStartable, isStoppable } from "@/lib/status";

interface Props {
  instance: Instance;
  onEdit?: () => void;
  onLogs?: () => void;
  onHandle?: () => void;
  compact?: boolean;
}

export function ServiceActions({ instance: i, onEdit, onLogs, onHandle, compact }: Props) {
  const { t } = useTranslation();
  const a = useServiceActions();
  const size = compact ? "xs" : "sm";

  let primary = null;
  if (i.status === "ERROR" && onHandle) {
    primary = (
      <Button size={size} color="red" variant="light" onClick={onHandle}>
        {t("services.action.handle")}
      </Button>
    );
  } else if (isStartable(i.status)) {
    primary = (
      <Button size={size} leftSection={<IconPlayerPlay size={14} />} onClick={() => a.start(i)} loading={a.pendingAction === "start"}>
        {t("services.action.start")}
      </Button>
    );
  } else if (isLoading(i.status)) {
    primary = (
      <Button size={size} variant="default" onClick={() => a.cancel(i)} loading={a.pendingAction === "cancel"}>
        {t("services.action.cancel")}
      </Button>
    );
  } else if (i.status === "READY" && i.gateway_state === "failed") {
    primary = (
      <Button size={size} color="yellow" variant="light" onClick={() => a.retryGateway(i)} loading={a.pendingAction === "gateway/retry"}>
        {t("services.action.retryGateway")}
      </Button>
    );
  } else if (i.status === "READY") {
    primary = (
      <Button size={size} variant="default" leftSection={<IconPlayerStop size={14} />} onClick={() => a.stop(i)} loading={a.pendingAction === "stop"}>
        {t("services.action.stop")}
      </Button>
    );
  }

  return (
    <Group gap="xs" wrap="nowrap">
      {primary}
      {!compact && i.status === "ERROR" && (
        <Button size={size} variant="default" leftSection={<IconRefresh size={14} />} onClick={() => a.start(i)} loading={a.pendingAction === "start"}>
          {t("services.action.restart")}
        </Button>
      )}
      {!compact && i.status === "READY" && (
        <Button size={size} variant="default" leftSection={<IconRefresh size={14} />} onClick={() => a.restart(i)} loading={a.pendingAction === "restart"}>
          {t("services.action.restart")}
        </Button>
      )}
      {!compact && onEdit && (
        <Button size={size} variant="default" onClick={onEdit} disabled={i.status === "STOPPING"}>
          {t("services.action.edit")}
        </Button>
      )}
      <Menu position="bottom-end" withinPortal>
        <Menu.Target>
          <ActionIcon variant="subtle" color="gray" aria-label="more">
            <IconDots size={16} />
          </ActionIcon>
        </Menu.Target>
        <Menu.Dropdown>
          {compact && (i.status === "READY" || i.status === "ERROR") && (
            <Menu.Item
              leftSection={<IconRefresh size={14} />}
              onClick={() => (i.status === "ERROR" ? a.start(i) : a.restart(i))}
            >
              {t("services.action.restart")}
            </Menu.Item>
          )}
          {compact && onEdit && <Menu.Item onClick={onEdit}>{t("services.action.edit")}</Menu.Item>}
          {onLogs && <Menu.Item onClick={onLogs}>{t("services.action.logs")}</Menu.Item>}
          {isStoppable(i.status) && i.status !== "READY" && (
            <Menu.Item leftSection={<IconPlayerStop size={14} />} onClick={() => a.stop(i)}>
              {t("services.action.stop")}
            </Menu.Item>
          )}
          <Menu.Divider />
          <Menu.Item
            color="red"
            leftSection={<IconTrash size={14} />}
            disabled={!isStartable(i.status)}
            title={!isStartable(i.status) ? t("services.confirm.deleteRunning") : undefined}
            onClick={() => a.remove(i)}
          >
            {t("services.action.delete")}
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>
    </Group>
  );
}
