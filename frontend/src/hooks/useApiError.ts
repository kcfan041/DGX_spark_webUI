import { notifications } from "@mantine/notifications";
import { useTranslation } from "react-i18next";
import { ApiError } from "@/api/client";

export function useApiErrorNotifier() {
  const { t } = useTranslation();
  return (err: unknown) => {
    const code = err instanceof ApiError ? err.code : "UNKNOWN";
    const reason = t(`errors.${code}.title`, { defaultValue: t(`errors.${code}`, { defaultValue: code }) });
    notifications.show({ color: "red", message: t("common.actionFailed", { reason }) });
  };
}
