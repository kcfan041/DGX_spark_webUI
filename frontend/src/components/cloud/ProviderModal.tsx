import { Alert, Anchor, Button, Group, Modal, PasswordInput, SegmentedControl, Stack, Text, TextInput } from "@mantine/core";
import { IconCheck, IconPlugConnected, IconX } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useCreateProvider, useProviderTypes, useTestProvider, useUpdateProvider } from "@/api/hooks";
import type { CloudProvider, ConnTestResult, ProviderType } from "@/api/types";
import { useApiErrorNotifier } from "@/hooks/useApiError";

const TYPES: ProviderType[] = ["openai", "anthropic", "gemini", "openai_compatible"];

export function ProviderModal({
  opened,
  editing,
  onClose,
  onCreated,
}: {
  opened: boolean;
  editing: CloudProvider | null;
  onClose: () => void;
  onCreated?: (p: CloudProvider) => void;
}) {
  const { t } = useTranslation();
  const specs = useProviderTypes();
  const create = useCreateProvider();
  const update = useUpdateProvider();
  const test = useTestProvider();
  const notifyError = useApiErrorNotifier();
  const [type, setType] = useState<ProviderType>("openai");
  const [name, setName] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiBase, setApiBase] = useState("");
  const [testModel, setTestModel] = useState("");
  const [result, setResult] = useState<ConnTestResult | null>(null);

  useEffect(() => {
    if (!opened) return;
    setType(editing?.type ?? "openai");
    setName(editing?.name ?? "");
    setApiKey("");
    setApiBase(editing?.api_base ?? "");
    setTestModel("");
    setResult(null);
    test.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened, editing]);

  const spec = specs.data?.find((s) => s.type === type);
  const needsBase = spec?.needs_api_base ?? type === "openai_compatible";
  const keyRequired = !editing && (spec?.api_key_required ?? type !== "openai_compatible");
  const canSave = name.trim() && (!keyRequired || apiKey.trim()) && (!needsBase || apiBase.trim());
  const canTest = editing
    ? Boolean(!needsBase || testModel.trim() || editing.models > 0)
    : (!keyRequired || apiKey.trim()) && (!needsBase || (apiBase.trim() && testModel.trim()));

  const runTest = () => {
    setResult(null);
    const body = { type, api_key: apiKey.trim() || null, api_base: apiBase.trim() || null, model: testModel.trim() || null };
    test.mutate(
      editing && !apiKey.trim() ? { id: editing.id, body: { model: testModel.trim() || null } } : { body },
      { onSuccess: setResult, onError: notifyError },
    );
  };

  const save = () => {
    if (editing) {
      update.mutate(
        {
          id: editing.id,
          body: { name: name.trim(), api_key: apiKey.trim() || null, api_base: needsBase ? apiBase.trim() || null : null },
        },
        { onSuccess: onClose, onError: notifyError },
      );
    } else {
      create.mutate(
        { type, name: name.trim(), api_key: apiKey.trim() || null, api_base: needsBase ? apiBase.trim() || null : null },
        {
          onSuccess: (p) => {
            onClose();
            onCreated?.(p);
          },
          onError: notifyError,
        },
      );
    }
  };

  return (
    <Modal opened={opened} onClose={onClose} title={editing ? t("cloud.provider.editTitle") : t("cloud.provider.addTitle")} size="lg">
      <Stack>
        {!editing && (
          <SegmentedControl
            fullWidth
            value={type}
            onChange={(v) => {
              setType(v as ProviderType);
              setResult(null);
              if (!name.trim() || TYPES.some((x) => t(`cloud.types.${x}`) === name)) setName(t(`cloud.types.${v}`));
            }}
            data={TYPES.map((x) => ({ value: x, label: t(`cloud.types.${x}`) }))}
            data-testid="provider-type"
          />
        )}
        <Text size="sm" c="dimmed">
          {t(`cloud.typeHelp.${type}`)}
        </Text>
        <TextInput
          label={t("cloud.provider.name")}
          description={t("cloud.provider.nameHelp")}
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
          maxLength={60}
          required
          data-testid="provider-name"
        />
        {needsBase && (
          <TextInput
            label={t("cloud.provider.apiBase")}
            description={t("cloud.provider.apiBaseHelp")}
            placeholder="https://api.example.com/v1"
            value={apiBase}
            onChange={(e) => {
              setApiBase(e.currentTarget.value);
              setResult(null);
            }}
            required
            data-testid="provider-base"
          />
        )}
        <PasswordInput
          label={t("cloud.provider.apiKey")}
          description={
            editing ? (
              t("cloud.provider.apiKeyKeep", { masked: editing.masked_key ?? "—" })
            ) : spec?.key_url ? (
              <>
                {t("cloud.provider.apiKeyWhere")}{" "}
                <Anchor href={spec.key_url} target="_blank" rel="noreferrer" size="xs">
                  {spec.key_url}
                </Anchor>
              </>
            ) : (
              t("cloud.provider.apiKeyOptional")
            )
          }
          value={apiKey}
          onChange={(e) => {
            setApiKey(e.currentTarget.value);
            setResult(null);
          }}
          required={keyRequired}
          autoComplete="off"
          data-testid="provider-key"
        />
        <Group align="flex-end" gap="xs">
          <TextInput
            style={{ flex: 1 }}
            label={t("cloud.provider.testModel")}
            description={
              spec?.test_model ? t("cloud.provider.testModelDefault", { model: spec.test_model }) : t("cloud.provider.testModelHelp")
            }
            placeholder={spec?.test_model ?? "model-name"}
            value={testModel}
            onChange={(e) => setTestModel(e.currentTarget.value)}
          />
          <Button
            variant="light"
            leftSection={<IconPlugConnected size={16} />}
            onClick={runTest}
            loading={test.isPending}
            disabled={!canTest}
            data-testid="provider-test"
          >
            {t("cloud.provider.test")}
          </Button>
        </Group>
        {result && (
          <Alert
            color={result.ok ? "teal" : "red"}
            icon={result.ok ? <IconCheck size={16} /> : <IconX size={16} />}
            data-testid="provider-test-result"
          >
            {result.ok ? t("cloud.provider.testOk", { model: result.model }) : t("cloud.provider.testFail", { model: result.model })}
            {result.error && (
              <Text size="xs" mt={4} style={{ wordBreak: "break-word" }}>
                {result.error}
              </Text>
            )}
          </Alert>
        )}
        <Text size="xs" c="dimmed">
          {t("cloud.provider.storage")}
        </Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={save} disabled={!canSave} loading={create.isPending || update.isPending} data-testid="provider-save">
            {t("common.save")}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
