import {
  Accordion,
  Alert,
  Badge,
  Button,
  Group,
  NumberInput,
  Select,
  Slider,
  Stack,
  Switch,
  Text,
  TextInput,
  Tooltip,
} from "@mantine/core";
import { IconAlertTriangle, IconHelpCircle } from "@tabler/icons-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { InstanceParams, ModelMeta, ParamField } from "@/api/types";
import { formatBytes, formatContext } from "@/lib/format";

export interface ServiceFormValues {
  display_name: string;
  served_model_name: string;
  params: InstanceParams;
  autostart: boolean;
  autostart_order: number;
}

interface Props {
  values: ServiceFormValues;
  onChange: (v: ServiceFormValues) => void;
  schema: ParamField[];
  model: ModelMeta | undefined;
  presetLabel: string;
  presetModified: boolean;
  onResetPreset: () => void;
  totalMemoryBytes?: number | null;
  originalServedName?: string;
}

function Label({ text, help }: { text: string; help: string }) {
  return (
    <Group gap={4} wrap="nowrap">
      <Text size="sm" fw={500}>
        {text}
      </Text>
      <Tooltip label={help} multiline w={280} withArrow>
        <IconHelpCircle size={15} style={{ color: "var(--mantine-color-dimmed)", cursor: "help" }} />
      </Tooltip>
    </Group>
  );
}

export function ServiceForm(props: Props) {
  const { t } = useTranslation();
  const { values, onChange, schema, model } = props;
  const field = (n: keyof InstanceParams) => schema.find((f) => f.name === n);
  const setParam = <K extends keyof InstanceParams>(k: K, v: InstanceParams[K]) =>
    onChange({ ...values, params: { ...values.params, [k]: v } });

  const ctx = field("max_model_len");
  const mem = field("gpu_memory_utilization");
  const quant = field("quantization");
  const dtype = field("dtype");
  const ctxMax = ctx?.max ?? model?.max_context ?? 131072;
  const ctxMin = ctx?.min ?? 256;
  const memMin = mem?.min ?? 0.1;
  const memMax = mem?.max ?? 0.95;
  const p = values.params;
  const renamed = props.originalServedName && props.originalServedName !== values.served_model_name;

  const quantOptions = (quant?.options ?? ["auto"]).map((o) => ({
    value: o,
    label:
      o === "auto"
        ? model?.quantization
          ? t("params.autoDetected", { value: model.quantization })
          : t("params.auto")
        : o,
  }));

  const basic: ReactNode = (
    <Stack gap="lg">
      <Group justify="space-between">
        <Badge variant="light" size="lg" styles={{ label: { textTransform: "none" } }}>
          {props.presetLabel}
          {props.presetModified && t("wizard.modified")}
        </Badge>
        {props.presetModified && (
          <Button variant="subtle" size="xs" onClick={props.onResetPreset}>
            {t("wizard.resetPreset")}
          </Button>
        )}
      </Group>

      <TextInput
        label={<Label text={t("params.display_name.label")} help={t("params.display_name.help")} />}
        value={values.display_name}
        onChange={(e) => onChange({ ...values, display_name: e.currentTarget.value })}
      />
      <TextInput
        label={<Label text={t("params.served_model_name.label")} help={t("params.served_model_name.help")} />}
        value={values.served_model_name}
        onChange={(e) => onChange({ ...values, served_model_name: e.currentTarget.value.toLowerCase() })}
        description={t("params.served_model_name.help")}
        error={renamed ? t("detail.renameWarning", { name: props.originalServedName }) : undefined}
      />

      <Stack gap={4}>
        <Label text={t("params.max_model_len.label")} help={t("params.max_model_len.help")} />
        <Group align="center" wrap="nowrap">
          <Slider
            style={{ flex: 1 }}
            min={ctxMin}
            max={ctxMax}
            step={256}
            value={Math.min(p.max_model_len, ctxMax)}
            onChange={(v) => setParam("max_model_len", v)}
            label={(v) => formatContext(v)}
            marks={(ctx?.marks ?? []).map((m) => ({ value: m, label: formatContext(m) }))}
            mb="lg"
          />
          <NumberInput
            w={110}
            min={ctxMin}
            step={1024}
            value={p.max_model_len}
            onChange={(v) => typeof v === "number" && setParam("max_model_len", v)}
            aria-label={t("params.max_model_len.label")}
          />
        </Group>
      </Stack>

      <Stack gap={4}>
        <Label text={t("params.gpu_memory_utilization.label")} help={t("params.gpu_memory_utilization.help")} />
        <Group align="center" wrap="nowrap">
          <Slider
            style={{ flex: 1 }}
            min={memMin}
            max={memMax}
            step={0.05}
            value={p.gpu_memory_utilization}
            onChange={(v) => setParam("gpu_memory_utilization", Math.round(v * 100) / 100)}
            label={(v) => `${Math.round(v * 100)}%`}
            marks={[0.3, 0.5, 0.7, 0.9].filter((m) => m >= memMin && m <= memMax).map((m) => ({ value: m, label: `${m * 100}%` }))}
            mb="lg"
          />
          <Text w={110} size="sm" ta="right">
            {Math.round(p.gpu_memory_utilization * 100)}%
            {props.totalMemoryBytes ? ` ≈ ${formatBytes(p.gpu_memory_utilization * props.totalMemoryBytes, 0)}` : ""}
          </Text>
        </Group>
      </Stack>

      <Select
        label={<Label text={t("params.quantization.label")} help={t("params.quantization.help")} />}
        data={quantOptions}
        value={p.quantization}
        onChange={(v) => v && setParam("quantization", v)}
        allowDeselect={false}
      />

      <Switch
        label={t("params.autostart.label")}
        description={t("params.autostart.help")}
        checked={values.autostart}
        onChange={(e) => onChange({ ...values, autostart: e.currentTarget.checked })}
      />
    </Stack>
  );

  return (
    <Stack>
      {basic}
      <Accordion variant="contained">
        <Accordion.Item value="advanced">
          <Accordion.Control>
            <Text fw={500}>{t("wizard.advanced")}</Text>
            <Text size="xs" c="dimmed">
              {t("wizard.advancedHint")}
            </Text>
          </Accordion.Control>
          <Accordion.Panel>
            <Stack>
              <Select
                label={<Label text={t("params.dtype.label")} help={t("params.dtype.help")} />}
                data={dtype?.options ?? ["auto"]}
                value={p.dtype}
                onChange={(v) => v && setParam("dtype", v)}
                allowDeselect={false}
              />
              <Switch
                label={t("params.trust_remote_code.label")}
                description={t("params.trust_remote_code.help")}
                checked={p.trust_remote_code}
                onChange={(e) => setParam("trust_remote_code", e.currentTarget.checked)}
              />
              {p.trust_remote_code && (
                <Alert color="yellow" icon={<IconAlertTriangle size={16} />}>
                  {t("params.trust_remote_code.warning")}
                </Alert>
              )}
              <NumberInput
                label={<Label text={t("params.host_port.label")} help={t("params.host_port.help")} />}
                min={1024}
                max={65535}
                value={p.host_port ?? ""}
                onChange={(v) => setParam("host_port", typeof v === "number" ? v : null)}
                allowDecimal={false}
              />
              <TextInput
                label={<Label text={t("params.extra_args.label")} help={t("params.extra_args.help")} />}
                value={p.extra_args}
                onChange={(e) => setParam("extra_args", e.currentTarget.value)}
                placeholder="--enforce-eager"
                description={p.extra_args ? t("params.extra_args.warning") : undefined}
                styles={{ input: { fontFamily: "monospace" } }}
              />
              <NumberInput
                label={<Label text={t("params.autostart_order.label")} help={t("params.autostart_order.help")} />}
                min={0}
                max={10000}
                value={values.autostart_order}
                onChange={(v) => typeof v === "number" && onChange({ ...values, autostart_order: v })}
                allowDecimal={false}
                disabled={!values.autostart}
              />
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
    </Stack>
  );
}
