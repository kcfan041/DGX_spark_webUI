import { Button, Group, Modal, Stack, Text, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useUpdateApiKey } from "@/api/hooks";
import type { ApiKeyInfo, KeyLimits } from "@/api/types";
import { KeyLimitsFields } from "@/components/gateway/KeyLimitsFields";
import { EMPTY_LIMITS } from "@/lib/usage";
import { useApiErrorNotifier } from "@/hooks/useApiError";
import { formatTime } from "@/lib/format";

export function EditKeyModal({ apiKey, onClose, models }: { apiKey: ApiKeyInfo | null; onClose: () => void; models: string[] }) {
  const { t } = useTranslation();
  const update = useUpdateApiKey();
  const notifyError = useApiErrorNotifier();
  const [name, setName] = useState("");
  const [limits, setLimits] = useState<KeyLimits>(EMPTY_LIMITS);

  useEffect(() => {
    if (apiKey) {
      setName(apiKey.name);
      setLimits(apiKey.limits);
    }
  }, [apiKey]);

  const save = () => {
    if (!apiKey) return;
    update.mutate(
      { id: apiKey.id, body: { name: name.trim() || apiKey.name, ...limits } },
      {
        onSuccess: () => {
          notifications.show({ color: "teal", message: t("keyLimits.saved", { name: name.trim() || apiKey.name }) });
          onClose();
        },
        onError: notifyError,
      },
    );
  };

  return (
    <Modal opened={apiKey !== null} onClose={onClose} title={t("keyLimits.editTitle")} size="lg">
      {apiKey && (
        <Stack>
          <TextInput label={t("gateway.keys.name")} value={name} onChange={(e) => setName(e.currentTarget.value)} maxLength={80} />
          <Group gap="lg">
            <Text size="sm" c="dimmed">
              {t("keyLimits.spent", { amount: apiKey.spend.toFixed(4) })}
            </Text>
            {apiKey.budget_reset_at && (
              <Text size="sm" c="dimmed">
                {t("keyLimits.resetsAt", { time: formatTime(apiKey.budget_reset_at) })}
              </Text>
            )}
            <Text size="sm" c="dimmed">
              {t("keyLimits.expiresAt", { time: apiKey.expires_at ? formatTime(apiKey.expires_at) : t("keyLimits.expiryNever") })}
            </Text>
          </Group>
          <KeyLimitsFields value={limits} onChange={setLimits} models={models} />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button onClick={save} loading={update.isPending} data-testid="save-limits">
              {t("common.save")}
            </Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}
