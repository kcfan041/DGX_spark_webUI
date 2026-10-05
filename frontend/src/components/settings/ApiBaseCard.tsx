import { Alert, Badge, Button, Card, Code, Group, Radio, Stack, Text, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconAlertTriangle, IconCheck, IconPlugConnected, IconX } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiError } from "@/api/client";
import { useApiBase, useUpdateApiBase } from "@/api/hooks";
import type { ApiBaseInfo } from "@/api/types";
import { QueryState } from "@/components/QueryState";
import { useApiErrorNotifier } from "@/hooks/useApiError";
import { probeGateway, type ProbeResult } from "@/lib/gatewayProbe";

const SOURCE_COLOR = { manual: "blue", deploy: "grape", auto: "teal" } as const;

export function ApiBaseWarnings({ warnings }: { warnings: string[] }) {
  const { t } = useTranslation();
  if (!warnings.length) return null;
  return (
    <Stack gap={6}>
      {warnings.map((w) => (
        <Alert key={w} color="yellow" icon={<IconAlertTriangle size={16} />} p="xs">
          <Text size="sm">{t(`apiBase.warnings.${w}`, { defaultValue: w })}</Text>
        </Alert>
      ))}
    </Stack>
  );
}

export function SourceBadge({ source }: { source: ApiBaseInfo["source"] }) {
  const { t } = useTranslation();
  return (
    <Badge size="sm" variant="light" color={SOURCE_COLOR[source]} data-testid="api-base-source">
      {t(`apiBase.source.${source}`)}
    </Badge>
  );
}

function ProbeButton({ value }: { value: string }) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ProbeResult | null>(null);
  useEffect(() => setResult(null), [value]);
  return (
    <Group gap="xs">
      <Button
        size="xs"
        variant="default"
        leftSection={<IconPlugConnected size={14} />}
        loading={busy}
        disabled={!value}
        data-testid="api-base-test"
        onClick={async () => {
          setBusy(true);
          setResult(await probeGateway(value));
          setBusy(false);
        }}
      >
        {t("apiBase.test")}
      </Button>
      {result &&
        (result.ok ? (
          <Text size="sm" c="teal" data-testid="api-base-test-result">
            <IconCheck size={14} style={{ verticalAlign: "middle" }} /> {t("apiBase.testOk", { ms: result.ms })}
          </Text>
        ) : (
          <Text size="sm" c="red" data-testid="api-base-test-result">
            <IconX size={14} style={{ verticalAlign: "middle" }} />{" "}
            {t(`apiBase.testFail.${result.reason}`, { status: result.status })}
          </Text>
        ))}
    </Group>
  );
}

export function ApiBaseCard() {
  const { t } = useTranslation();
  const q = useApiBase();
  const update = useUpdateApiBase();
  const notifyError = useApiErrorNotifier();
  const info = q.data;
  const [mode, setMode] = useState<"auto" | "manual">("auto");
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!info) return;
    setMode(info.source === "manual" ? "manual" : "auto");
    setValue(info.manual ?? info.deploy ?? info.auto);
  }, [info]);

  const save = (body: { mode: "auto" | "manual" | null; value?: string | null }) => {
    setError(null);
    update.mutate(body, {
      onSuccess: () => notifications.show({ color: "teal", message: t("apiBase.saved") }),
      onError: (e) => {
        if (e instanceof ApiError && e.code === "API_BASE_INVALID") setError(t("apiBase.invalid"));
        else notifyError(e);
      },
    });
  };

  return (
    <Card withBorder data-testid="api-base-card">
      <Group justify="space-between" mb="xs">
        <Text fw={600}>{t("apiBase.title")}</Text>
        {info && <SourceBadge source={info.source} />}
      </Group>
      <Text size="sm" c="dimmed" mb="sm">
        {t("apiBase.intro")}
      </Text>
      <QueryState isLoading={q.isLoading} error={q.error}>
        {info && (
          <Stack>
            <Group gap="xs">
              <Text size="sm">{t("apiBase.current")}</Text>
              <Code data-testid="api-base-effective">{info.effective}</Code>
            </Group>
            <ApiBaseWarnings warnings={info.warnings} />

            <Radio.Group value={mode} onChange={(v) => setMode(v as "auto" | "manual")}>
              <Stack gap="sm">
                <Radio
                  value="auto"
                  data-testid="api-base-mode-auto"
                  label={t("apiBase.autoLabel")}
                  description={
                    <>
                      {t("apiBase.autoHelp")} <Code>{info.auto}</Code>
                    </>
                  }
                />
                <Radio
                  value="manual"
                  data-testid="api-base-mode-manual"
                  label={t("apiBase.manualLabel")}
                  description={t("apiBase.manualHelp")}
                />
              </Stack>
            </Radio.Group>

            {mode === "manual" && (
              <TextInput
                value={value}
                onChange={(e) => {
                  setValue(e.currentTarget.value);
                  setError(null);
                }}
                placeholder="http://192.168.1.10:4000/v1"
                error={error}
                styles={{ input: { fontFamily: "monospace" } }}
                data-testid="api-base-input"
              />
            )}

            {info.deploy && info.source === "deploy" && (
              <Text size="xs" c="dimmed">
                {t("apiBase.deployNote", { value: info.deploy })}
              </Text>
            )}

            <Group justify="space-between">
              <ProbeButton value={mode === "manual" ? value.trim() : info.auto} />
              <Group gap="xs">
                {info.mode !== null && info.deploy && (
                  <Button size="xs" variant="subtle" onClick={() => save({ mode: null })} loading={update.isPending}>
                    {t("apiBase.reset")}
                  </Button>
                )}
                <Button
                  size="xs"
                  data-testid="api-base-save"
                  loading={update.isPending}
                  disabled={mode === "manual" && !value.trim()}
                  onClick={() => save(mode === "manual" ? { mode, value: value.trim() } : { mode })}
                >
                  {t("common.save")}
                </Button>
              </Group>
            </Group>
          </Stack>
        )}
      </QueryState>
    </Card>
  );
}
