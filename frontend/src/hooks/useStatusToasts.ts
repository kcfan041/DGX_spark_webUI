import { notifications } from "@mantine/notifications";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useInstances } from "@/api/hooks";
import type { InstanceStatus } from "@/api/types";

export function useStatusToasts() {
  const { t } = useTranslation();
  const { data } = useInstances();
  const prev = useRef<Map<string, InstanceStatus> | null>(null);

  useEffect(() => {
    if (!data) return;
    const current = new Map(data.map((i) => [i.id, i.status]));
    if (prev.current) {
      for (const i of data) {
        const before = prev.current.get(i.id);
        if (!before || before === i.status) continue;
        if (i.status === "READY") {
          notifications.show({ color: "teal", message: t("services.toast.ready", { name: i.display_name }) });
        } else if (i.status === "ERROR") {
          const reason = i.last_error ? t(`errors.${i.last_error.code}.title`, { defaultValue: i.last_error.code }) : "";
          notifications.show({ color: "red", message: t("services.toast.error", { name: i.display_name, reason }), autoClose: 10000 });
        }
      }
    }
    prev.current = current;
  }, [data, t]);
}
