import { Anchor, Badge, Button, Card, Divider, Group, NumberInput, Stack, Switch, Text, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconCheck, IconPlugConnected, IconX } from "@tabler/icons-react";
import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ApiError } from "@/api/client";
import { useAdvancedSettings, useTestHfEndpoint, useUpdateAdvanced } from "@/api/hooks";
import type { AdvancedField, AdvancedUpdate, SettingSource } from "@/api/types";
import { QueryState } from "@/components/QueryState";
import { useApiErrorNotifier } from "@/hooks/useApiError";

const SOURCE_COLOR: Record<SettingSource, string> = { web: "blue", deploy: "grape", default: "gray" };

function Row({
  title,
  help,
  source,
  onReset,
  children,
}: {
  title: string;
  help: string;
  source: SettingSource;
  onReset: () => void;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <Stack gap={6}>
      <Group justify="space-between">
        <Group gap="xs">
          <Text size="sm" fw={500}>
            {title}
          </Text>
          <Badge size="xs" variant="light" color={SOURCE_COLOR[source]}>
            {t(`advanced.source.${source}`)}
          </Badge>
        </Group>
        {source === "web" && (
          <Anchor size="xs" component="button" type="button" onClick={onReset}>
            {t("advanced.reset")}
          </Anchor>
        )}
      </Group>
      <Text size="xs" c="dimmed">
        {help}
      </Text>
      {children}
    </Stack>
  );
}

export function AdvancedCard() {
  const { t } = useTranslation();
  const q = useAdvancedSettings();
  const update = useUpdateAdvanced();
  const test = useTestHfEndpoint();
  const notifyError = useApiErrorNotifier();
  const s = q.data;
  const [endpoint, setEndpoint] = useState("");
  const [timeout, setTimeoutMin] = useState<number | string>(15);
  const [endpointError, setEndpointError] = useState<string | null>(null);

  useEffect(() => {
    if (!s) return;
    setEndpoint(s.hf_endpoint.value ?? "");
    setTimeoutMin(s.health_timeout_min.value);
  }, [s]);

  const save = (body: AdvancedUpdate, message: string) =>
    update.mutate(body, {
      onSuccess: () => notifications.show({ color: "teal", message }),
      onError: (e) => {
        if (e instanceof ApiError && e.code === "HF_ENDPOINT_INVALID") setEndpointError(t("advanced.endpointInvalid"));
        else notifyError(e);
      },
    });
  const reset = (f: AdvancedField) => save({ reset: [f] }, t("advanced.resetDone"));

  const [lo, hi] = s?.timeout_range ?? [15, 120];
  const timeoutNum = typeof timeout === "number" ? timeout : Number(timeout);
  const timeoutValid = Number.isInteger(timeoutNum) && timeoutNum >= lo && timeoutNum <= hi;

  return (
    <Card withBorder data-testid="advanced-card">
      <Text fw={600} mb="xs">
        {t("advanced.title")}
      </Text>
      <Text size="sm" c="dimmed" mb="md">
        {t("advanced.intro")}
      </Text>
      <QueryState isLoading={q.isLoading} error={q.error}>
        {s && (
          <Stack gap="lg">
            <Row
              title={t("advanced.timeout")}
              help={t("advanced.timeoutHelp", { lo, hi, def: s.health_timeout_min.default })}
              source={s.health_timeout_min.source}
              onReset={() => reset("health_timeout_min")}
            >
              <Group gap="xs" align="flex-start">
                <NumberInput
                  w={140}
                  min={lo}
                  max={hi}
                  step={5}
                  allowDecimal={false}
                  suffix={` ${t("advanced.minutes")}`}
                  value={timeout}
                  onChange={setTimeoutMin}
                  error={!timeoutValid ? t("advanced.timeoutRange", { lo, hi }) : undefined}
                  data-testid="timeout-input"
                />
                <Button
                  size="sm"
                  variant="default"
                  disabled={!timeoutValid || timeoutNum === s.health_timeout_min.value}
                  loading={update.isPending}
                  onClick={() => save({ health_timeout_min: timeoutNum }, t("advanced.saved"))}
                  data-testid="timeout-save"
                >
                  {t("common.save")}
                </Button>
              </Group>
            </Row>

            <Divider />

            <Row
              title={t("advanced.endpoint")}
              help={t("advanced.endpointHelp")}
              source={s.hf_endpoint.source}
              onReset={() => reset("hf_endpoint")}
            >
              <Group gap="xs" align="flex-start">
                <TextInput
                  style={{ flex: 1 }}
                  placeholder="https://huggingface.co"
                  value={endpoint}
                  onChange={(e) => {
                    setEndpoint(e.currentTarget.value);
                    setEndpointError(null);
                    test.reset();
                  }}
                  error={endpointError}
                  styles={{ input: { fontFamily: "monospace" } }}
                  data-testid="endpoint-input"
                />
                <Button
                  size="sm"
                  variant="default"
                  leftSection={<IconPlugConnected size={14} />}
                  loading={test.isPending}
                  onClick={() =>
                    test.mutate(endpoint.trim() || null, {
                      onError: (e) =>
                        e instanceof ApiError && e.code === "HF_ENDPOINT_INVALID"
                          ? setEndpointError(t("advanced.endpointInvalid"))
                          : notifyError(e),
                    })
                  }
                  data-testid="endpoint-test"
                >
                  {t("advanced.test")}
                </Button>
                <Button
                  size="sm"
                  variant="default"
                  loading={update.isPending}
                  disabled={(endpoint.trim() || null) === (s.hf_endpoint.value ?? null)}
                  onClick={() => save({ hf_endpoint: endpoint.trim() || null }, t("advanced.saved"))}
                  data-testid="endpoint-save"
                >
                  {t("common.save")}
                </Button>
              </Group>
              {test.data && (
                <Text size="sm" c={test.data.ok ? "teal" : "red"} data-testid="endpoint-test-result">
                  {test.data.ok ? <IconCheck size={14} /> : <IconX size={14} />}{" "}
                  {test.data.ok
                    ? t("advanced.testOk", { url: test.data.url, ms: test.data.ms })
                    : t(`advanced.testFail.${test.data.reason}`, { url: test.data.url, status: test.data.status })}
                </Text>
              )}
            </Row>

            <Divider />

            <Row
              title={t("advanced.verbose")}
              help={t("advanced.verboseHelp")}
              source={s.verbose_access_log.source}
              onReset={() => reset("verbose_access_log")}
            >
              <Switch
                checked={s.verbose_access_log.value}
                onChange={(e) =>
                  save(
                    { verbose_access_log: e.currentTarget.checked },
                    e.currentTarget.checked ? t("advanced.verboseOn") : t("advanced.verboseOff"),
                  )
                }
                label={s.verbose_access_log.value ? t("advanced.on") : t("advanced.off")}
                data-testid="verbose-switch"
              />
            </Row>
          </Stack>
        )}
      </QueryState>
    </Card>
  );
}
