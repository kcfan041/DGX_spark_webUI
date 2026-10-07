import {
  Badge,
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
import { useAdvancedSettings, useModelSources, useSystemInfo } from "@/api/hooks";
import { QueryState } from "@/components/QueryState";
import { AdminTokenCard } from "@/components/settings/AdminTokenCard";
import { AdvancedCard } from "@/components/settings/AdvancedCard";
import { ApiBaseCard } from "@/components/settings/ApiBaseCard";
import { HfTokenCard } from "@/components/settings/HfTokenCard";
import { setLanguage, type Language } from "@/i18n";

export function SettingsPage() {
  const { t, i18n } = useTranslation();
  const info = useSystemInfo();
  const sources = useModelSources();
  const adv = useAdvancedSettings();
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

      <AdminTokenCard />

      <ApiBaseCard />

      <HfTokenCard />

      <AdvancedCard />

      <Card withBorder>
        <Text fw={600} mb="xs">
          {t("settings.runtime")}
        </Text>
        <Text size="xs" c="dimmed" mb="sm">
          {t("settings.runtimeHelp")}
        </Text>
        <QueryState isLoading={info.isLoading} error={info.error}>
          {info.data && (
            <Table>
              <Table.Tbody>
                <Table.Tr>
                  <Table.Td w={220}>{t("settings.profile")}</Table.Td>
                  <Table.Td>{info.data.profile}</Table.Td>
                </Table.Tr>
                <Table.Tr>
                  <Table.Td>{t("settings.image")}</Table.Td>
                  <Table.Td>
                    <Code style={{ wordBreak: "break-all" }}>{info.data.vllm_image}</Code>
                  </Table.Td>
                </Table.Tr>
                {adv.data && (
                  <>
                    <Table.Tr>
                      <Table.Td>{t("settings.modelRoot")}</Table.Td>
                      <Table.Td>
                        <Code>{adv.data.deploy.model_root}</Code>
                        {adv.data.deploy.model_owner && (
                          <Text span size="xs" c="dimmed">
                            {" "}
                            {t("settings.owner", { owner: adv.data.deploy.model_owner })}
                          </Text>
                        )}
                      </Table.Td>
                    </Table.Tr>
                    <Table.Tr>
                      <Table.Td>{t("settings.gateway")}</Table.Td>
                      <Table.Td>
                        port <Code>{adv.data.deploy.gateway_port}</Code>{" "}
                        <Badge size="sm" variant="light" color={adv.data.deploy.gateway_local_only ? "yellow" : "teal"}>
                          {adv.data.deploy.gateway_local_only ? t("settings.localOnly") : t("settings.lanOpen")}
                        </Badge>
                      </Table.Td>
                    </Table.Tr>
                  </>
                )}
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
