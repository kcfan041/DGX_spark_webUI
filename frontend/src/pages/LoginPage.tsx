import { Alert, Button, Center, Paper, PasswordInput, Stack, Title } from "@mantine/core";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";

export function LoginPage() {
  const { t } = useTranslation();
  const { authenticated, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/dashboard";
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (authenticated) return <Navigate to={from} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(token.trim());
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? t("login.invalid") : t("login.networkError"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Center h="100vh" bg="gray.0">
      <Paper withBorder shadow="sm" p="xl" w={380}>
        <form onSubmit={submit}>
          <Stack>
            <Title order={3}>{t("app.title")}</Title>
            <Title order={5} c="dimmed">
              {t("login.title")}
            </Title>
            <PasswordInput
              label={t("login.tokenLabel")}
              placeholder={t("login.tokenPlaceholder")}
              value={token}
              onChange={(e) => setToken(e.currentTarget.value)}
              autoFocus
              required
            />
            {error && <Alert color="red">{error}</Alert>}
            <Button type="submit" loading={busy} disabled={!token.trim()}>
              {t("login.submit")}
            </Button>
          </Stack>
        </form>
      </Paper>
    </Center>
  );
}
