import { Accordion, Button, Group, NumberInput, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocalPrice, useSetLocalPrice } from "@/api/hooks";
import { useApiErrorNotifier } from "@/hooks/useApiError";

export function LocalPriceCard({ instanceId }: { instanceId: string }) {
  const { t } = useTranslation();
  const q = useLocalPrice(instanceId);
  const set = useSetLocalPrice(instanceId);
  const notifyError = useApiErrorNotifier();
  const [pin, setIn] = useState<number | string>(0);
  const [pout, setOut] = useState<number | string>(0);

  useEffect(() => {
    if (q.data) {
      setIn(q.data.input_per_mtok);
      setOut(q.data.output_per_mtok);
    }
  }, [q.data]);

  const dirty = q.data && (Number(pin) !== q.data.input_per_mtok || Number(pout) !== q.data.output_per_mtok);
  const summary =
    q.data && (q.data.input_per_mtok || q.data.output_per_mtok)
      ? t("price.summary", { input: q.data.input_per_mtok, output: q.data.output_per_mtok })
      : t("price.free");

  return (
    <Accordion variant="contained">
      <Accordion.Item value="price">
        <Accordion.Control data-testid="price-toggle">
          <Group gap="xs">
            <Text size="sm">{t("price.title")}</Text>
            <Text size="xs" c="dimmed">
              {summary}
            </Text>
          </Group>
        </Accordion.Control>
        <Accordion.Panel>
          <Stack gap="sm">
            <Text size="xs" c="dimmed">
              {t("price.help")}
            </Text>
            <Group grow>
              <NumberInput
                label={t("price.input")}
                prefix="$ "
                min={0}
                max={1000}
                decimalScale={4}
                value={pin}
                onChange={setIn}
                data-testid="price-in"
              />
              <NumberInput
                label={t("price.output")}
                prefix="$ "
                min={0}
                max={1000}
                decimalScale={4}
                value={pout}
                onChange={setOut}
                data-testid="price-out"
              />
            </Group>
            <Group justify="flex-end">
              <Button
                size="xs"
                disabled={!dirty}
                loading={set.isPending}
                onClick={() =>
                  set.mutate(
                    { input_per_mtok: Number(pin) || 0, output_per_mtok: Number(pout) || 0 },
                    {
                      onSuccess: () => notifications.show({ color: "teal", message: t("price.saved") }),
                      onError: notifyError,
                    },
                  )
                }
                data-testid="price-save"
              >
                {t("common.save")}
              </Button>
            </Group>
          </Stack>
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  );
}
