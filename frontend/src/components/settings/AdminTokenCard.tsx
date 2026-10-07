import { Badge, Button, Card, Group, PasswordInput, Stack, Text } from "@mantine/core";
import { modals } from "@mantine/modals";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiError } from "@/api/client";
import { useAdminTokenInfo, useChangeAdminToken } from "@/api/hooks";
import { useAuth } from "@/auth/AuthContext";
import { useApiErrorNotifier } from "@/hooks/useApiError";

const MIN = 12;

export function AdminTokenCard() {
  const { t } = useTranslation();
  const info = useAdminTokenInfo();
  const change = useChangeAdminToken();
  const notifyError = useApiErrorNotifier();
  const { logout } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const tooShort = next.length > 0 && next.length < MIN;
  const hasSpace = /\s/.test(next);
  const mismatch = confirm.length > 0 && confirm !== next;
  const ok = current && next.length >= MIN && !hasSpace && next === confirm;

  const submit = () => {
    setErr(null);
    change.mutate(
      { current, new: next },
      {
        onSuccess: () => {
          modals.open({
            title: t("adminToken.doneTitle"),
            withCloseButton: false,
            closeOnClickOutside: false,
            closeOnEscape: false,
            children: (
              <Stack>
                <Text size="sm">{t("adminToken.doneBody")}</Text>
                <Group justify="flex-end">
                  <Button
                    onClick={() => {
                      modals.closeAll();
                      logout();
                    }}
                    data-testid="token-relogin"
                  >
                    {t("adminToken.relogin")}
                  </Button>
                </Group>
              </Stack>
            ),
          });
        },
        onError: (e) => {
          if (e instanceof ApiError && ["TOKEN_CURRENT_WRONG", "TOKEN_WEAK", "TOKEN_SAME"].includes(e.code))
            setErr(t(`adminToken.err.${e.code}`));
          else notifyError(e);
        },
      },
    );
  };

  return (
    <Card withBorder data-testid="admin-token-card">
      <Group justify="space-between" mb="xs">
        <Text fw={600}>{t("adminToken.title")}</Text>
        {info.data && (
          <Badge variant="light" color={info.data.source === "web" ? "blue" : "grape"}>
            {t(`adminToken.source.${info.data.source}`)}
          </Badge>
        )}
      </Group>
      <Text size="sm" c="dimmed" mb="sm">
        {t("adminToken.intro")}
      </Text>
      <Stack gap="xs">
        <PasswordInput
          label={t("adminToken.current")}
          value={current}
          onChange={(e) => setCurrent(e.currentTarget.value)}
          autoComplete="current-password"
          data-testid="token-current"
        />
        <PasswordInput
          label={t("adminToken.new")}
          description={t("adminToken.rule", { n: MIN })}
          value={next}
          onChange={(e) => setNext(e.currentTarget.value)}
          error={tooShort ? t("adminToken.tooShort", { n: MIN }) : hasSpace ? t("adminToken.noSpace") : undefined}
          autoComplete="new-password"
          data-testid="token-new"
        />
        <PasswordInput
          label={t("adminToken.confirm")}
          value={confirm}
          onChange={(e) => setConfirm(e.currentTarget.value)}
          error={mismatch ? t("adminToken.mismatch") : undefined}
          autoComplete="new-password"
          data-testid="token-confirm"
        />
        {err && (
          <Text size="sm" c="red" data-testid="token-error">
            {err}
          </Text>
        )}
        <Text size="xs" c="dimmed">
          {t("adminToken.note")}
        </Text>
        <Group justify="flex-end">
          <Button size="xs" disabled={!ok} loading={change.isPending} onClick={submit} data-testid="token-save">
            {t("adminToken.save")}
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}
