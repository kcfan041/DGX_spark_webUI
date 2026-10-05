import { Accordion, Alert, Button, Code, Group, Stack, Text } from "@mantine/core";
import { IconAlertTriangle, IconX } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import type { InstanceError, Suggestion } from "@/api/types";
import { formatContext, formatTime } from "@/lib/format";

interface Props {
  error: InstanceError;
  onSuggestion: (s: Suggestion) => void;
  onViewLogs: () => void;
}

export function ErrorCard({ error, onSuggestion, onViewLogs }: Props) {
  const { t } = useTranslation();
  const warning = error.severity === "warning";
  return (
    <Alert
      color={warning ? "yellow" : "red"}
      icon={warning ? <IconAlertTriangle /> : <IconX />}
      title={t(`errors.${error.code}.title`, { defaultValue: error.code })}
      data-testid="error-card"
    >
      <Stack gap="sm">
        <Text size="sm">{t(`errors.${error.code}.description`, { defaultValue: "", ...error.params })}</Text>
        {error.suggestions.length > 0 && (
          <Stack gap={4}>
            <Text size="sm" fw={500}>
              {t("detail.suggestions")}
            </Text>
            <Group gap="xs">
              {error.suggestions.map((s) => (
                <Button key={s.label_key} size="xs" variant="white" color={warning ? "yellow" : "red"} onClick={() => onSuggestion(s)}>
                  {t(s.label_key, {
                    defaultValue: s.action,
                    value: typeof s.params?.value === "number" ? formatContext(s.params.value) : s.params?.value,
                  })}
                </Button>
              ))}
            </Group>
          </Stack>
        )}
        {error.evidence.length > 0 && (
          <Accordion variant="filled" chevronPosition="left">
            <Accordion.Item value="ev">
              <Accordion.Control>
                <Text size="sm">
                  {t("detail.relatedLog")}（{error.evidence.length}）
                </Text>
              </Accordion.Control>
              <Accordion.Panel>
                <Code block style={{ whiteSpace: "pre-wrap", fontSize: 11 }}>
                  {error.evidence.join("\n")}
                </Code>
              </Accordion.Panel>
            </Accordion.Item>
          </Accordion>
        )}
        <Group justify="space-between">
          <Text size="xs" c="dimmed">
            {t("detail.errorCode", { code: error.code, time: formatTime(error.occurred_at) })}
          </Text>
          <Button size="xs" variant="subtle" onClick={onViewLogs}>
            {t("detail.viewRawLog")}
          </Button>
        </Group>
      </Stack>
    </Alert>
  );
}
