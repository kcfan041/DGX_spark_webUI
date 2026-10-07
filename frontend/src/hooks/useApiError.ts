import { notifications } from "@mantine/notifications";
import { useTranslation } from "react-i18next";
import { ApiError } from "@/api/client";

export function useApiErrorNotifier() {
  const { t } = useTranslation();
  return (err: unknown) => {
    const code = err instanceof ApiError ? err.code : "UNKNOWN";
    const detail = err instanceof ApiError ? err.detail : null;
    const params =
      detail && typeof detail === "object" && "params" in detail && detail.params && typeof detail.params === "object"
        ? (detail.params as Record<string, unknown>)
        : {};
    const reason = t(`errors.${code}.title`, {
      ...params,
      defaultValue: t(`errors.${code}`, { ...params, defaultValue: code }),
    });
    notifications.show({ color: "red", message: t("common.actionFailed", { reason }) });
  };
}
