import { Alert, Group, Select, Stack, Title } from "@mantine/core";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { useInstances } from "@/api/hooks";
import { LogViewer } from "@/components/service/LogViewer";

export function LogsPage() {
  const { t } = useTranslation();
  const instances = useInstances();
  const [search, setSearch] = useSearchParams();
  const source = search.get("source");
  const options = (instances.data ?? []).map((i) => ({ value: i.id, label: `${i.display_name}（${t(`status.${i.status}`)}）` }));

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={3}>{t("logs.title")}</Title>
        <Select
          w={360}
          label={t("logs.source")}
          placeholder={t("logs.noSource")}
          data={options}
          value={source}
          onChange={(v) => setSearch(v ? { source: v } : {}, { replace: true })}
          searchable
        />
      </Group>
      {source ? <LogViewer instanceId={source} height={600} /> : <Alert>{t("logs.noSource")}</Alert>}
    </Stack>
  );
}
