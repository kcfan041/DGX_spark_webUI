import { Group, MultiSelect, NumberInput, Select, Stack, Text } from "@mantine/core";
import { useTranslation } from "react-i18next";
import type { BudgetPeriod, KeyLimits } from "@/api/types";



const num = (v: string | number): number | null => (v === "" || v === null || Number(v) <= 0 ? null : Number(v));

export function KeyLimitsFields({
  value,
  onChange,
  models,
}: {
  value: KeyLimits;
  onChange: (v: KeyLimits) => void;
  models: string[];
}) {
  const { t } = useTranslation();
  const set = (patch: Partial<KeyLimits>) => onChange({ ...value, ...patch });
  const modelOptions = Array.from(new Set([...models, ...value.models])).sort();

  return (
    <Stack gap="sm">
      <Text size="xs" c="dimmed">
        {t("keyLimits.intro")}
      </Text>
      <MultiSelect
        label={t("keyLimits.models")}
        description={t("keyLimits.modelsHelp")}
        placeholder={value.models.length ? undefined : t("keyLimits.allModels")}
        data={modelOptions}
        value={value.models}
        onChange={(models) => set({ models })}
        searchable
        clearable
        data-testid="limit-models"
      />
      <Group grow align="flex-start">
        <NumberInput
          label={t("keyLimits.budget")}
          description={t("keyLimits.budgetHelp")}
          placeholder={t("keyLimits.unlimited")}
          prefix="$ "
          min={0}
          decimalScale={2}
          value={value.max_budget ?? ""}
          onChange={(v) => {
            const b = num(v);
            set({ max_budget: b, budget_duration: b ? (value.budget_duration ?? "30d") : null });
          }}
          data-testid="limit-budget"
        />
        <Select
          label={t("keyLimits.period")}
          description={t("keyLimits.periodHelp")}
          disabled={!value.max_budget}
          data={[
            { value: "none", label: t("keyLimits.periodNone") },
            { value: "1d", label: t("keyLimits.period1d") },
            { value: "7d", label: t("keyLimits.period7d") },
            { value: "30d", label: t("keyLimits.period30d") },
          ]}
          value={value.budget_duration ?? "none"}
          onChange={(v) => set({ budget_duration: v && v !== "none" ? (v as BudgetPeriod) : null })}
          allowDeselect={false}
        />
      </Group>
      <Group grow align="flex-start">
        <NumberInput
          label={t("keyLimits.rpm")}
          description={t("keyLimits.rpmHelp")}
          placeholder={t("keyLimits.unlimited")}
          min={0}
          allowDecimal={false}
          thousandSeparator=","
          value={value.rpm_limit ?? ""}
          onChange={(v) => set({ rpm_limit: num(v) })}
          data-testid="limit-rpm"
        />
        <NumberInput
          label={t("keyLimits.tpm")}
          description={t("keyLimits.tpmHelp")}
          placeholder={t("keyLimits.unlimited")}
          min={0}
          allowDecimal={false}
          thousandSeparator=","
          value={value.tpm_limit ?? ""}
          onChange={(v) => set({ tpm_limit: num(v) })}
        />
      </Group>
    </Stack>
  );
}
