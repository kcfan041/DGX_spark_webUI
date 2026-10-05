import { Text } from "@mantine/core";
import { modals } from "@mantine/modals";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useDeleteInstance, useLifecycle, type LifecycleAction } from "@/api/hooks";
import type { Instance } from "@/api/types";
import { useApiErrorNotifier } from "./useApiError";

export function useServiceActions() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const lifecycle = useLifecycle();
  const del = useDeleteInstance();
  const notifyError = useApiErrorNotifier();

  const run = (inst: Instance, action: LifecycleAction) =>
    lifecycle.mutate({ id: inst.id, action }, { onError: notifyError });

  const confirm = (titleKey: string, bodyKey: string, inst: Instance, onConfirm: () => void, danger = false) =>
    modals.openConfirmModal({
      title: t(titleKey),
      children: <Text size="sm">{t(bodyKey, { name: inst.served_model_name })}</Text>,
      labels: { confirm: t("common.confirm"), cancel: t("common.cancel") },
      confirmProps: { color: danger ? "red" : undefined },
      onConfirm,
    });

  return {
    pending: lifecycle.isPending || del.isPending,
    pendingAction: lifecycle.isPending ? lifecycle.variables?.action : undefined,
    start: (inst: Instance) => run(inst, "start"),
    cancel: (inst: Instance) => run(inst, "cancel"),
    retryGateway: (inst: Instance) => run(inst, "gateway/retry"),
    stop: (inst: Instance) =>
      inst.gateway_state === "registered"
        ? confirm("services.confirm.stopTitle", "services.confirm.stopBody", inst, () => run(inst, "stop"))
        : run(inst, "stop"),
    restart: (inst: Instance) =>
      inst.gateway_state === "registered"
        ? confirm("services.confirm.restartTitle", "services.confirm.restartBody", inst, () => run(inst, "restart"))
        : run(inst, "restart"),
    remove: (inst: Instance, after?: () => void) =>
      confirm(
        "services.confirm.deleteTitle",
        "services.confirm.deleteBody",
        inst,
        () =>
          del.mutate(inst.id, {
            onSuccess: () => (after ? after() : navigate("/services")),
            onError: notifyError,
          }),
        true,
      ),
  };
}
