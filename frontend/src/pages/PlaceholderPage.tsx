import { Alert, Stack, Title } from "@mantine/core";
import { useTranslation } from "react-i18next";

export function PlaceholderPage({ titleKey }: { titleKey: string }) {
  const { t } = useTranslation();
  return (
    <Stack>
      <Title order={3}>{t(titleKey)}</Title>
      <Alert>{t("common.comingSoon")}</Alert>
    </Stack>
  );
}
