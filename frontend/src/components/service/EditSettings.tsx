import { Alert, Anchor, Button, Group, Loader, SegmentedControl, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconAlertTriangle } from "@tabler/icons-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useLifecycle,
  useModels,
  useParamSchema,
  usePresets,
  usePreview,
  useSystemSummary,
  useUpdateInstance,
} from "@/api/hooks";
import type { Instance, InstanceParams, PlanInput } from "@/api/types";
import { useApiErrorNotifier } from "@/hooks/useApiError";
import { useDebounced } from "@/hooks/useDebounced";
import { isLoading } from "@/lib/status";
import { WarningList } from "./PlanSummary";
import { ServiceForm, type ServiceFormValues } from "./ServiceForm";

export interface EditSettingsHandle {
  patch?: Partial<InstanceParams>;
  preset?: string;
}

interface Props {
  instance: Instance;
  initial?: EditSettingsHandle | null;
  onDone: () => void;
}

function fromInstance(i: Instance): ServiceFormValues {
  return {
    display_name: i.display_name,
    served_model_name: i.served_model_name,
    params: { ...i.params },
    autostart: i.autostart,
    autostart_order: i.autostart_order,
  };
}

export function EditSettings({ instance, initial, onDone }: Props) {
  const { t } = useTranslation();
  const notifyError = useApiErrorNotifier();
  const models = useModels();
  const summary = useSystemSummary();
  const [presetId, setPresetId] = useState(initial?.preset ?? instance.preset);
  const presets = usePresets(instance.model_id);
  const schema = useParamSchema(instance.model_id, presetId);
  const update = useUpdateInstance(instance.id);
  const model = models.data?.find((m) => m.id === instance.model_id);
  const preset = presets.data?.find((p) => p.id === presetId);

  const [values, setValues] = useState<ServiceFormValues>(() => {
    const v = fromInstance(instance);
    if (initial?.patch) v.params = { ...v.params, ...initial.patch };
    return v;
  });

  useEffect(() => {
    if (initial?.preset && preset) setValues((v) => ({ ...v, params: { ...preset.params, host_port: v.params.host_port, extra_args: v.params.extra_args } }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preset?.id]);

  const input: PlanInput = useMemo(
    () => ({
      model_id: instance.model_id,
      preset: presetId,
      params: values.params,
      display_name: values.display_name,
      served_model_name: values.served_model_name,
      autostart: values.autostart,
      autostart_order: values.autostart_order,
    }),
    [instance.model_id, presetId, values],
  );
  const preview = usePreview(useDebounced(input, 300), instance.id);
  const lifecycle = useLifecycle();
  const running = instance.status === "READY" || isLoading(instance.status);
  const blocked = Boolean(preview.data?.blocking);
  const retryable = instance.status === "ERROR";

  const saveAndRetry = () =>
    update.mutate(
      {
        preset: presetId,
        params: values.params,
        display_name: values.display_name,
        served_model_name: values.served_model_name,
        autostart: values.autostart,
        autostart_order: values.autostart_order,
      },
      {
        onSuccess: () =>
          lifecycle.mutate(
            { id: instance.id, action: "start" },
            { onSuccess: () => onDone(), onError: notifyError },
          ),
        onError: notifyError,
      },
    );

  const save = (restart: boolean) =>
    update.mutate(
      {
        preset: presetId,
        params: values.params,
        display_name: values.display_name,
        served_model_name: values.served_model_name,
        autostart: values.autostart,
        autostart_order: values.autostart_order,
        restart,
      },
      {
        onSuccess: () => {
          notifications.show({ color: "teal", message: t("services.toast.saved") });
          onDone();
        },
        onError: notifyError,
      },
    );

  if (!schema.data || !presets.data) return <Loader />;

  const presetModified = Boolean(
    preset &&
      (preset.params.max_model_len !== values.params.max_model_len ||
        Math.abs(preset.params.gpu_memory_utilization - values.params.gpu_memory_utilization) > 1e-6 ||
        preset.params.quantization !== values.params.quantization),
  );

  return (
    <Stack>
      {running && (
        <Alert color="yellow" icon={<IconAlertTriangle size={16} />}>
          {t("detail.restartRequired")}
        </Alert>
      )}
      <Stack gap={4}>
        <Text size="sm" fw={500}>
          {t("wizard.step.preset")}
        </Text>
        <SegmentedControl
          value={presetId}
          onChange={(id) => {
            setPresetId(id);
            const p = presets.data?.find((x) => x.id === id);
            if (p) setValues((v) => ({ ...v, params: { ...p.params, host_port: v.params.host_port, extra_args: v.params.extra_args } }));
          }}
          data={presets.data.map((p) => ({ value: p.id, label: t(`presets.${p.id}.label`) }))}
        />
      </Stack>
      <ServiceForm
        values={values}
        onChange={setValues}
        schema={schema.data}
        model={model}
        presetLabel={t(`presets.${presetId}.label`)}
        presetModified={presetModified}
        onResetPreset={() =>
          preset && setValues((v) => ({ ...v, params: { ...preset.params, host_port: v.params.host_port, extra_args: v.params.extra_args } }))
        }
        totalMemoryBytes={summary.data?.memory?.total_bytes}
        originalServedName={instance.served_model_name}
      />
      {preview.data && <WarningList warnings={preview.data.warnings} />}
      <Group justify="flex-end">
        <Anchor size="sm" component="button" type="button" onClick={onDone}>
          {t("common.cancel")}
        </Anchor>
        {running ? (
          <>
            <Button variant="default" onClick={() => save(false)} loading={update.isPending} disabled={blocked}>
              {t("detail.saveOnly")}
            </Button>
            <Button onClick={() => save(true)} loading={update.isPending} disabled={blocked}>
              {t("detail.saveAndRestart")}
            </Button>
          </>
        ) : retryable ? (
          <>
            <Button variant="default" onClick={() => save(false)} loading={update.isPending} disabled={blocked}>
              {t("common.save")}
            </Button>
            <Button onClick={saveAndRetry} loading={update.isPending || lifecycle.isPending} disabled={blocked}>
              {t("detail.saveAndRetry")}
            </Button>
          </>
        ) : (
          <Button onClick={() => save(false)} loading={update.isPending} disabled={blocked}>
            {t("common.save")}
          </Button>
        )}
      </Group>
    </Stack>
  );
}
