import { ActionIcon, Alert, Anchor, Button, Card, Code, CopyButton, Group, Stack, Tabs, Text, Textarea, Tooltip } from "@mantine/core";
import { IconCheck, IconCopy, IconPlayerPlay } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useTestInstance } from "@/api/hooks";
import type { Instance } from "@/api/types";
import { useApiErrorNotifier } from "@/hooks/useApiError";

export function CopyValue({ value, label }: { value: string; label?: string }) {
  const { t } = useTranslation();
  return (
    <Group gap={6} wrap="nowrap">
      {label && (
        <Text size="sm" c="dimmed" w={110}>
          {label}
        </Text>
      )}
      <Code>{value}</Code>
      <CopyButton value={value}>
        {({ copied, copy }) => (
          <Tooltip label={copied ? t("common.copied") : t("common.copy")}>
            <ActionIcon variant="subtle" color={copied ? "teal" : "gray"} onClick={copy} size="sm">
              {copied ? <IconCheck size={14} /> : <IconCopy size={14} />}
            </ActionIcon>
          </Tooltip>
        )}
      </CopyButton>
    </Group>
  );
}

function examples(base: string, model: string) {
  return {
    curl: `curl ${base}/chat/completions \\
  -H "Authorization: Bearer <YOUR_API_KEY>" \\
  -H "Content-Type: application/json" \\
  -d '{"model": "${model}", "messages": [{"role": "user", "content": "你好"}]}'`,
    python: `from openai import OpenAI

client = OpenAI(base_url="${base}", api_key="<YOUR_API_KEY>")
resp = client.chat.completions.create(
    model="${model}",
    messages=[{"role": "user", "content": "你好"}],
)
print(resp.choices[0].message.content)`,
    opencode: `{
  "provider": {
    "dgx-spark": {
      "npm": "@ai-sdk/openai-compatible",
      "options": { "baseURL": "${base}", "apiKey": "<YOUR_API_KEY>" },
      "models": { "${model}": {} }
    }
  }
}`,
  };
}

export function HowToUse({ instance }: { instance: Instance }) {
  const { t } = useTranslation();
  const test = useTestInstance(instance.id);
  const notifyError = useApiErrorNotifier();
  const [content, setContent] = useState(t("detail.testDefault"));
  const ex = examples(instance.endpoint.api_base, instance.endpoint.model);
  const canTest = instance.status === "READY" && instance.gateway_state === "registered";

  return (
    <Card withBorder>
      <Text fw={600} mb="sm">
        {t("detail.howToUse")}
      </Text>
      <Stack gap="xs">
        <CopyValue label={t("detail.apiBase")} value={instance.endpoint.api_base} />
        <CopyValue label={t("detail.modelName")} value={instance.endpoint.model} />
        <Group gap={6}>
          <Text size="sm" c="dimmed" w={110}>
            {t("detail.apiKey")}
          </Text>
          <Text size="sm">{t("detail.apiKeyHint")}</Text>
          <Anchor component={Link} to="/gateway" size="sm">
            {t("detail.goGateway")}
          </Anchor>
        </Group>
        <Tabs defaultValue="curl" mt="xs">
          <Tabs.List>
            <Tabs.Tab value="curl">curl</Tabs.Tab>
            <Tabs.Tab value="python">Python</Tabs.Tab>
            <Tabs.Tab value="opencode">OpenCode</Tabs.Tab>
          </Tabs.List>
          {(Object.keys(ex) as (keyof typeof ex)[]).map((k) => (
            <Tabs.Panel key={k} value={k} pt="xs">
              <Group align="flex-start" wrap="nowrap">
                <Code block style={{ flex: 1, fontSize: 11 }}>
                  {ex[k]}
                </Code>
                <CopyButton value={ex[k]}>
                  {({ copied, copy }) => (
                    <ActionIcon variant="subtle" color={copied ? "teal" : "gray"} onClick={copy}>
                      {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
                    </ActionIcon>
                  )}
                </CopyButton>
              </Group>
            </Tabs.Panel>
          ))}
        </Tabs>

        <Stack gap="xs" mt="sm">
          <Textarea value={content} onChange={(e) => setContent(e.currentTarget.value)} autosize minRows={1} maxRows={4} />
          <Group>
            <Tooltip label={t("detail.testOnlyReady")} disabled={canTest}>
              <Button
                leftSection={<IconPlayerPlay size={14} />}
                onClick={() => test.mutate(content, { onError: notifyError })}
                loading={test.isPending}
                disabled={!canTest || !content.trim()}
                data-testid="send-test"
              >
                {t("detail.test")}
              </Button>
            </Tooltip>
          </Group>
          {test.data &&
            (test.data.ok ? (
              <Alert color="teal" title={t("detail.testOk", { ms: test.data.latency_ms })}>
                <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>
                  {test.data.reply_preview}
                </Text>
              </Alert>
            ) : (
              <Alert color="red" title={t("detail.testFailed")}>
                {t(`errors.${test.data.error}.title`, { defaultValue: test.data.error ?? "" })}
              </Alert>
            ))}
        </Stack>
      </Stack>
    </Card>
  );
}
