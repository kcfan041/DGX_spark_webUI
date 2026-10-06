import { Badge, Button, Card, Group, PasswordInput, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useHfToken, useSetHfToken } from "@/api/hooks";
import { useApiErrorNotifier } from "@/hooks/useApiError";

export function HfTokenCard() {
  const { t } = useTranslation();
  const q = useHfToken();
  const set = useSetHfToken();
  const notifyError = useApiErrorNotifier();
  const [value, setValue] = useState("");
  const status = q.data;

  return (
    <Card withBorder data-testid="hf-token-card">
      <Group justify="space-between" mb="xs">
        <Text fw={600}>{t("hfToken.title")}</Text>
        {status && (
          <Badge variant="light" color={status.configured ? "teal" : "gray"}>
            {status.configured ? t(`hfToken.source.${status.source}`) : t("hfToken.none")}
          </Badge>
        )}
      </Group>
      <Text size="sm" c="dimmed" mb="sm">
        {t("hfToken.intro")}
      </Text>
      <Stack gap="xs">
        <PasswordInput
          placeholder="hf_..."
          value={value}
          onChange={(e) => setValue(e.currentTarget.value)}
          data-testid="hf-token-input"
        />
        <Group justify="flex-end" gap="xs">
          {status?.source === "web" && (
            <Button
              variant="subtle"
              size="xs"
              color="red"
              loading={set.isPending}
              onClick={() =>
                set.mutate(null, {
                  onSuccess: () => notifications.show({ color: "teal", message: t("hfToken.cleared") }),
                  onError: notifyError,
                })
              }
            >
              {t("hfToken.clear")}
            </Button>
          )}
          <Button
            size="xs"
            disabled={!value.trim()}
            loading={set.isPending}
            onClick={() =>
              set.mutate(value.trim(), {
                onSuccess: () => {
                  setValue("");
                  notifications.show({ color: "teal", message: t("hfToken.saved") });
                },
                onError: notifyError,
              })
            }
          >
            {t("common.save")}
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}
