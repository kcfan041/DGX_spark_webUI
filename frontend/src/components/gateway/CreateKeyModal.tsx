import { Accordion, Alert, Button, Checkbox, Code, Group, Modal, Select, Stack, Text, TextInput } from "@mantine/core";
import { CopyButton } from "@/components/CopyButton";
import { IconAlertTriangle, IconCheck, IconCopy } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useCreateApiKey } from "@/api/hooks";
import type { CreatedApiKey, KeyExpiry, KeyLimits } from "@/api/types";
import { KeyLimitsFields } from "@/components/gateway/KeyLimitsFields";
import { EMPTY_LIMITS } from "@/lib/usage";
import { useApiErrorNotifier } from "@/hooks/useApiError";

interface Props {
  opened: boolean;
  onClose: () => void;
  apiBase: string;
  exampleModel: string | null;
  models?: string[];
  rotated?: CreatedApiKey | null;
}

function Copy({ value, label, testId }: { value: string; label: string; testId?: string }) {
  const { t } = useTranslation();
  return (
    <CopyButton value={value}>
      {({ copied, failed, copy }) => (
        <Button
          size="xs"
          variant={copied ? "filled" : "light"}
          color={copied ? "teal" : failed ? "red" : undefined}
          leftSection={copied ? <IconCheck size={14} /> : <IconCopy size={14} />}
          onClick={copy}
          data-testid={testId}
        >
          {copied ? t("common.copied") : failed ? t("common.copyFailed") : label}
        </Button>
      )}
    </CopyButton>
  );
}

export function CreateKeyModal({ opened, onClose, apiBase, exampleModel, models = [], rotated = null }: Props) {
  const { t } = useTranslation();
  const create = useCreateApiKey();
  const notifyError = useApiErrorNotifier();
  const [name, setName] = useState("");
  const [expiry, setExpiry] = useState<KeyExpiry | null>(null);
  const [limits, setLimits] = useState<KeyLimits>(EMPTY_LIMITS);
  const [createdState, setCreated] = useState<CreatedApiKey | null>(null);
  const [saved, setSaved] = useState(false);
  const created = rotated ?? createdState;

  const reset = () => {
    setName("");
    setExpiry(null);
    setLimits(EMPTY_LIMITS);
    setCreated(null);
    setSaved(false);
    create.reset();
  };

  const close = () => {
    if (created && !saved) return;
    reset();
    onClose();
  };

  const submit = () =>
    create.mutate({ name: name.trim(), expires_in: expiry, ...limits }, {
      onSuccess: (k) => setCreated(k),
      onError: notifyError,
    });

  const snippet = created
    ? `curl ${apiBase}/chat/completions \\
  -H "Authorization: Bearer ${created.key}" \\
  -H "Content-Type: application/json" \\
  -d '{"model": "${exampleModel ?? "<MODEL_NAME>"}", "messages": [{"role": "user", "content": "${t("common.sampleHello")}"}]}'`
    : "";

  return (
    <Modal
      opened={opened}
      onClose={close}
      title={rotated ? t("gateway.keys.rotatedTitle") : created ? t("gateway.keys.createdTitle") : t("gateway.keys.createTitle")}
      size="lg"
      closeOnClickOutside={!created}
      closeOnEscape={!created}
      withCloseButton={!created}
    >
      {!created ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) submit();
          }}
        >
          <Stack>
            <TextInput
              label={t("gateway.keys.name")}
              description={t("gateway.keys.nameHelp")}
              placeholder={t("gateway.keys.namePlaceholder")}
              value={name}
              onChange={(e) => setName(e.currentTarget.value)}
              maxLength={80}
              data-autofocus
              required
            />
            <Select
              label={t("keyLimits.expiry")}
              data={[
                { value: "never", label: t("keyLimits.expiryNever") },
                { value: "7d", label: t("keyLimits.expiry7d") },
                { value: "30d", label: t("keyLimits.expiry30d") },
                { value: "90d", label: t("keyLimits.expiry90d") },
                { value: "365d", label: t("keyLimits.expiry365d") },
              ]}
              value={expiry ?? "never"}
              onChange={(v) => setExpiry(v && v !== "never" ? (v as KeyExpiry) : null)}
              allowDeselect={false}
            />
            <Accordion variant="contained">
              <Accordion.Item value="limits">
                <Accordion.Control data-testid="limits-toggle">{t("keyLimits.title")}</Accordion.Control>
                <Accordion.Panel>
                  <KeyLimitsFields value={limits} onChange={setLimits} models={models} />
                </Accordion.Panel>
              </Accordion.Item>
            </Accordion>
            <Group justify="flex-end">
              <Button variant="default" onClick={close}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" loading={create.isPending} disabled={!name.trim()}>
                {t("gateway.keys.create")}
              </Button>
            </Group>
          </Stack>
        </form>
      ) : (
        <Stack>
          <Text size="sm">
            {t("gateway.keys.name")}
            {t("common.colon")}
            <b>{created.name}</b>
          </Text>
          <Code block data-testid="new-key" style={{ fontSize: 14, wordBreak: "break-all", userSelect: "all" }}>
            {created.key}
          </Code>
          <Alert color="yellow" icon={<IconAlertTriangle size={16} />}>
            {t("gateway.keys.onlyOnce")}
          </Alert>
          {rotated && (
            <Text size="sm" c="dimmed">
              {t("gateway.keys.rotatedNote")}
            </Text>
          )}
          <Group gap="xs">
            <Copy value={created.key} label={t("gateway.keys.copyKey")} testId="copy-key" />
            <Copy value={apiBase} label={t("gateway.keys.copyBase")} />
            <Copy value={snippet} label={t("gateway.keys.copyExample")} />
          </Group>
          <Checkbox
            label={t("gateway.keys.savedConfirm")}
            checked={saved}
            onChange={(e) => setSaved(e.currentTarget.checked)}
            data-testid="saved-confirm"
          />
          <Group justify="flex-end">
            <Button onClick={close} disabled={!saved} data-testid="close-created">
              {t("gateway.keys.savedClose")}
            </Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}
