import { Alert, Anchor, Button, Card, Center, Group, Loader, Stack, Stepper, Text, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useCreateInstance, useModels, useParamSchema, usePresets, usePreview, useSystemSummary } from "@/api/hooks";
import type { InstanceParams, PlanInput, ResolvedPreset } from "@/api/types";
import { ModelPicker } from "@/components/service/ModelPicker";
import { PlanSummary } from "@/components/service/PlanSummary";
import { PresetCards } from "@/components/service/PresetCards";
import { ServiceForm, type ServiceFormValues } from "@/components/service/ServiceForm";
import { useApiErrorNotifier } from "@/hooks/useApiError";
import { useDebounced } from "@/hooks/useDebounced";

function shortName(name: string) {
  return name.split("/").pop() ?? name;
}

function slug(name: string) {
  return shortName(name).toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^[-._]+|[-._]+$/g, "").slice(0, 63) || "model";
}

function sameParams(a: InstanceParams, b: InstanceParams) {
  return (
    a.max_model_len === b.max_model_len &&
    Math.abs(a.gpu_memory_utilization - b.gpu_memory_utilization) < 1e-6 &&
    a.quantization === b.quantization &&
    a.dtype === b.dtype &&
    a.trust_remote_code === b.trust_remote_code
  );
}

export function CreateServicePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const notifyError = useApiErrorNotifier();
  const models = useModels();
  const summary = useSystemSummary();
  const create = useCreateInstance();

  const initialModel = search.get("model");
  const [step, setStep] = useState(initialModel ? 1 : 0);
  const [modelId, setModelId] = useState<string | null>(initialModel);
  const [presetId, setPresetId] = useState("balanced");
  const [values, setValues] = useState<ServiceFormValues | null>(null);

  const model = models.data?.find((m) => m.id === modelId);
  const presets = usePresets(modelId);
  const schema = useParamSchema(modelId, presetId);
  const preset: ResolvedPreset | undefined = presets.data?.find((p) => p.id === presetId);

  const applyPreset = (p: ResolvedPreset | undefined, keepNames = true) => {
    if (!p || !model) return;
    const autoName = (id: string) => `${shortName(model.name)}（${t(`presets.${id}.label`)}）`;
    setValues((prev) => ({
      display_name:
        keepNames && prev && !(presets.data ?? []).some((x) => autoName(x.id) === prev.display_name)
          ? prev.display_name
          : autoName(p.id),
      served_model_name: keepNames && prev ? prev.served_model_name : slug(model.name),
      params: { ...p.params, host_port: prev?.params.host_port ?? null, extra_args: prev?.params.extra_args ?? "" },
      autostart: prev?.autostart ?? false,
      autostart_order: prev?.autostart_order ?? 100,
    }));
  };

  useEffect(() => {
    setValues(null);
    setPresetId("balanced");
  }, [modelId]);

  useEffect(() => {
    if (preset && model) applyPreset(preset, values !== null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preset?.id, model?.id, presets.data]);

  useEffect(() => {
    if (step > 0 && modelId && models.data && !model) setStep(0);
  }, [step, modelId, model, models.data]);

  const planInput: PlanInput | null = useMemo(
    () =>
      model && values
        ? {
            model_id: model.id,
            preset: presetId,
            params: values.params,
            display_name: values.display_name || null,
            served_model_name: values.served_model_name || null,
            autostart: values.autostart,
            autostart_order: values.autostart_order,
          }
        : null,
    [model, values, presetId],
  );
  const preview = usePreview(useDebounced(planInput, 300));
  const plan = preview.data;
  const dirty = values !== null;

  useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  const submit = (start: boolean) => {
    if (!planInput) return;
    create.mutate(
      { ...planInput, start },
      {
        onSuccess: (inst) => {
          if (!start) notifications.show({ color: "teal", message: t("wizard.savedOnly") });
          navigate(`/services/${inst.id}`);
        },
        onError: notifyError,
      },
    );
  };

  const presetModified = Boolean(preset && values && !sameParams(values.params, preset.params));
  const canNext = [Boolean(model), Boolean(preset), Boolean(values), false][step];

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={3}>{t("wizard.title")}</Title>
        <Anchor
          size="sm"
          onClick={() => {
            if (!dirty || window.confirm(t("wizard.leaveConfirm"))) navigate(-1);
          }}
        >
          {t("common.cancel")}
        </Anchor>
      </Group>
      <Text c="dimmed" size="sm">
        {t("wizard.intro")}
      </Text>

      <Stepper active={step} onStepClick={(s) => s < step && setStep(s)} allowNextStepsSelect={false}>
        <Stepper.Step label={t("wizard.step.model")} description={model ? shortName(model.name) : undefined}>
          <Card withBorder>
            <Text fw={500} mb="sm">
              {t("wizard.selectModel")}
            </Text>
            {models.isLoading ? <Loader /> : <ModelPicker models={models.data ?? []} value={modelId} onChange={setModelId} />}
          </Card>
        </Stepper.Step>

        <Stepper.Step label={t("wizard.step.preset")} description={preset ? t(`presets.${preset.id}.label`) : undefined}>
          <Stack>
            <Text fw={500}>{t("wizard.selectPreset")}</Text>
            {presets.isLoading ? (
              <Center py="lg">
                <Loader />
              </Center>
            ) : (
              <PresetCards presets={presets.data ?? []} value={presetId} onChange={setPresetId} />
            )}
          </Stack>
        </Stepper.Step>

        <Stepper.Step label={t("wizard.step.settings")}>
          {values && schema.data ? (
            <ServiceForm
              values={values}
              onChange={setValues}
              schema={schema.data}
              model={model}
              presetLabel={t(`presets.${presetId}.label`)}
              presetModified={presetModified}
              onResetPreset={() => applyPreset(preset, true)}
              totalMemoryBytes={summary.data?.memory?.total_bytes}
            />
          ) : (
            <Loader />
          )}
          {plan && plan.warnings.some((w) => w.level === "blocking") && (
            <Alert color="red" mt="md">
              {t("errors.PLAN_BLOCKED")}
            </Alert>
          )}
        </Stepper.Step>

        <Stepper.Step label={t("wizard.step.confirm")}>
          {plan && model ? <PlanSummary plan={plan} modelName={model.name} /> : <Loader />}
        </Stepper.Step>
      </Stepper>

      <Group justify="space-between" mt="md">
        <Button variant="default" onClick={() => setStep((s) => s - 1)} disabled={step === 0}>
          {t("common.back")}
        </Button>
        {step < 3 ? (
          <Button onClick={() => setStep((s) => s + 1)} disabled={!canNext}>
            {t("common.next")}
          </Button>
        ) : (
          <Stack gap={4} align="flex-end">
            <Button
              size="md"
              onClick={() => submit(true)}
              loading={create.isPending}
              disabled={!plan || plan.blocking || preview.isFetching}
              data-testid="create-and-start"
            >
              ▶ {t("wizard.createAndStart")}
            </Button>
            <Anchor
              size="sm"
              c="dimmed"
              component="button"
              type="button"
              onClick={() => submit(false)}
              disabled={!plan || plan.blocking || create.isPending}
            >
              {t("wizard.saveOnly")}
            </Anchor>
          </Stack>
        )}
      </Group>
    </Stack>
  );
}
