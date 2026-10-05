import { Alert, Button, Center, Loader } from "@mantine/core";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

interface Props {
  isLoading: boolean;
  error: unknown;
  onRetry?: () => void;
  children: ReactNode;
}

export function QueryState({ isLoading, error, onRetry, children }: Props) {
  const { t } = useTranslation();
  if (isLoading)
    return (
      <Center py="xl">
        <Loader />
      </Center>
    );
  if (error)
    return (
      <Alert color="red" title={t("common.loadFailed")}>
        {onRetry && (
          <Button size="xs" variant="light" onClick={onRetry}>
            {t("common.retry")}
          </Button>
        )}
      </Alert>
    );
  return <>{children}</>;
}
