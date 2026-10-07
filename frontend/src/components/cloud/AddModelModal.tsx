import { Autocomplete, Button, Group, Modal, NumberInput, Select, Stack, Switch, Text, TextInput } from "@mantine/core";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAddCloudModel, useCatalog } from "@/api/hooks";
import type { CloudProvider } from "@/api/types";
import { useApiErrorNotifier } from "@/hooks/useApiError";

const NAME_RE = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$/;

export function AddModelModal({
  opened,
  onClose,
  providers,
  initialProvider,
}: {
  opened: boolean;
  onClose: () => void;
  providers: CloudProvider[];
  initialProvider: string | null;
}) {
  const { t } = useTranslation();
  const add = useAddCloudModel();
  const notifyError = useApiErrorNotifier();
  const [providerId, setProviderId] = useState<string | null>(null);
  const [model, setModel] = useState("");
  const [name, setName] = useState("");
  const [customPrice, setCustomPrice] = useState(false);
  const [priceIn, setPriceIn] = useState<number | string>(0);
  const [priceOut, setPriceOut] = useState<number | string>(0);

  useEffect(() => {
    if (!opened) return;
    setProviderId(initialProvider ?? providers[0]?.id ?? null);
    setModel("");
    setName("");
    setCustomPrice(false);
    setPriceIn(0);
    setPriceOut(0);
    add.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened, initialProvider]);

  const provider = providers.find((p) => p.id === providerId) ?? null;
  const catalog = useCatalog(provider && provider.type !== "openai_compatible" ? provider.type : null);
  const entry = useMemo(() => catalog.data?.find((m) => m.id === model.trim()), [catalog.data, model]);
  const suggestedName = model.trim().split("/").pop() ?? "";
  const finalName = name.trim() || suggestedName;
  const nameOk = !finalName || NAME_RE.test(finalName);
  const isCompat = provider?.type === "openai_compatible";

  const save = () => {
    if (!provider) return;
    add.mutate(
      {
        provider_id: provider.id,
        model: model.trim(),
        name: name.trim() || null,
        input_per_mtok: customPrice ? Number(priceIn) || 0 : null,
        output_per_mtok: customPrice ? Number(priceOut) || 0 : null,
      },
      { onSuccess: onClose, onError: notifyError },
    );
  };

  return (
    <Modal opened={opened} onClose={onClose} title={t("cloud.model.addTitle")} size="lg">
      <Stack>
        <Select
          label={t("cloud.model.provider")}
          data={providers.map((p) => ({ value: p.id, label: t("common.paren", { text: p.name, inner: t(`cloud.types.${p.type}`) }) }))}
          value={providerId}
          onChange={setProviderId}
          allowDeselect={false}
          data-testid="model-provider"
        />
        <Autocomplete
          label={t("cloud.model.model")}
          description={isCompat ? t("cloud.model.modelHelpCompat") : t("cloud.model.modelHelp")}
          placeholder={isCompat ? "llama-3.3-70b" : "gpt-4o-mini"}
          data={(catalog.data ?? []).map((m) => m.id)}
          value={model}
          onChange={setModel}
          limit={50}
          maxDropdownHeight={280}
          required
          data-testid="model-id"
        />
        {entry && (entry.input_per_mtok !== null || entry.output_per_mtok !== null) && (
          <Text size="xs" c="dimmed" data-testid="model-list-price">
            {t("cloud.model.listPrice", {
              input: entry.input_per_mtok ?? "—",
              output: entry.output_per_mtok ?? "—",
            })}
            {entry.max_input_tokens ? ` · ${t("cloud.model.context", { n: entry.max_input_tokens.toLocaleString() })}` : ""}
          </Text>
        )}
        <TextInput
          label={t("cloud.model.name")}
          description={t("cloud.model.nameHelp")}
          placeholder={suggestedName}
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
          error={nameOk ? undefined : t("cloud.model.nameInvalid")}
          maxLength={100}
          data-testid="model-name"
        />
        <Switch
          label={t("cloud.model.customPrice")}
          description={isCompat ? t("cloud.model.customPriceCompat") : t("cloud.model.customPriceHelp")}
          checked={customPrice}
          onChange={(e) => setCustomPrice(e.currentTarget.checked)}
        />
        {customPrice && (
          <Group grow>
            <NumberInput label={t("price.input")} prefix="$ " min={0} decimalScale={4} value={priceIn} onChange={setPriceIn} />
            <NumberInput label={t("price.output")} prefix="$ " min={0} decimalScale={4} value={priceOut} onChange={setPriceOut} />
          </Group>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={save} disabled={!provider || !model.trim() || !nameOk} loading={add.isPending} data-testid="model-save">
            {t("cloud.model.add")}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
