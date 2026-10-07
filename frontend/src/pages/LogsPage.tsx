import { Alert, Group, Select, Stack, Title } from "@mantine/core";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { useLogSources } from "@/api/hooks";
import { LogViewer } from "@/components/service/LogViewer";

export function LogsPage() {
  const { t } = useTranslation();
  const sources = useLogSources();
  const [search, setSearch] = useSearchParams();
  const legacy = search.get("source");
  const source = legacy && !legacy.includes(":") && !["gateway", "backend"].includes(legacy) ? `service:${legacy}` : legacy;

  const services = (sources.data ?? []).filter((s) => s.kind === "service");
  const platform = (sources.data ?? []).filter((s) => s.kind === "platform");
  const data = [
    {
      group: t("logs.groupServices"),
      items: services.map((s) => ({
        value: s.id,
        label: t("common.paren", { text: s.name, inner: t(`status.${s.status}`, { defaultValue: s.status ?? "" }) }),
      })),
    },
    {
      group: t("logs.groupPlatform"),
      items: platform.map((s) => ({ value: s.id, label: t(`logs.platform.${s.id}`, { defaultValue: s.name }) })),
    },
  ].filter((g) => g.items.length > 0);

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={3}>{t("logs.title")}</Title>
        <Select
          w={380}
          label={t("logs.source")}
          placeholder={t("logs.noSource")}
          data={data}
          value={source}
          onChange={(v) => setSearch(v ? { source: v } : {}, { replace: true })}
          searchable
          data-testid="log-source"
        />
      </Group>
      {source ? (
        <LogViewer key={source} source={source} height={600} />
      ) : (
        <Alert>{t("logs.noSource")}</Alert>
      )}
    </Stack>
  );
}
