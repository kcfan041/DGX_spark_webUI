import {
  Card,
  Code,
  SegmentedControl,
  Stack,
  Table,
  Text,
  Title,
  useMantineColorScheme,
  type MantineColorScheme,
} from "@mantine/core";
import { useTranslation } from "react-i18next";
import { useModelSources, useSystemInfo } from "@/api/hooks";
import { QueryState } from "@/components/QueryState";
import { setLanguage, type Language } from "@/i18n";

export function SettingsPage() {
  const { t, i18n } = useTranslation();
  const info = useSystemInfo();
  const sources = useModelSources();
  const { colorScheme, setColorScheme } = useMantineColorScheme();

  return (
    <Stack>
      <Title order={3}>{t("settings.title")}</Title>

      <Card withBorder>
        <Text fw={600} mb="sm">
          {t("settings.general")}
        </Text>
        <Text size="sm" mb={4}>
          {t("settings.language")}
        </Text>
        <SegmentedControl
          value={i18n.language}
          onChange={(v) => setLanguage(v as Language)}
          data={[
            { value: "zh-TW", label: "繁體中文" },
            { value: "en", label: "English" },
          ]}
        />
        <Text size="sm" mb={4} mt="md">
          {t("theme.label")}
        </Text>
        <SegmentedControl
          value={colorScheme}
          onChange={(v) => setColorScheme(v as MantineColorScheme)}
          data={[
            { value: "light", label: t("theme.light") },
            { value: "dark", label: t("theme.dark") },
            { value: "auto", label: t("theme.auto") },
          ]}
          data-testid="theme-setting"
        />
      </Card>

      <Card withBorder>
        <Text fw={600} mb="sm">
          {t("settings.runtime")}
        </Text>
        <QueryState isLoading={info.isLoading} error={info.error}>
          {info.data && (
            <Table>
              <Table.Tbody>
                <Table.Tr>
                  <Table.Td>{t("settings.profile")}</Table.Td>
                  <Table.Td>{info.data.profile}</Table.Td>
                </Table.Tr>
                <Table.Tr>
                  <Table.Td>{t("settings.image")}</Table.Td>
                  <Table.Td>
                    <Code>{info.data.vllm_image}</Code>
                  </Table.Td>
                </Table.Tr>
                <Table.Tr>
                  <Table.Td>{t("settings.version")}</Table.Td>
                  <Table.Td>{info.data.version}</Table.Td>
                </Table.Tr>
              </Table.Tbody>
            </Table>
          )}
        </QueryState>
      </Card>

      <Card withBorder>
        <Text fw={600} mb="sm">
          {t("settings.sources")}
        </Text>
        <QueryState isLoading={sources.isLoading} error={sources.error}>
          <Table>
            <Table.Tbody>
              {(sources.data ?? []).map((s) => (
                <Table.Tr key={s.id}>
                  <Table.Td>{s.type}</Table.Td>
                  <Table.Td>
                    <Code>{s.path}</Code>
                  </Table.Td>
                  <Table.Td>{s.model_count}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </QueryState>
      </Card>
    </Stack>
  );
}
