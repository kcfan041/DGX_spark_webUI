import { AppShell, Burger, Button, Group, NavLink, Text, ThemeIcon, Title } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
  IconBox,
  IconCircleFilled,
  IconFileText,
  IconLayoutDashboard,
  IconRoute,
  IconServer,
  IconSettings,
} from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { NavLink as RouterLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useSystemSummary } from "@/api/hooks";
import { useAuth } from "@/auth/AuthContext";

const NAV = [
  { to: "/dashboard", key: "nav.dashboard", icon: IconLayoutDashboard },
  { to: "/models", key: "nav.models", icon: IconBox },
  { to: "/services", key: "nav.services", icon: IconServer },
  { to: "/gateway", key: "nav.gateway", icon: IconRoute },
  { to: "/logs", key: "nav.logs", icon: IconFileText },
  { to: "/settings", key: "nav.settings", icon: IconSettings },
] as const;

const HEALTH_COLOR = { ok: "green", attention: "yellow", gateway_unreachable: "red", runtime_error: "red" } as const;

export function AppLayout() {
  const { t } = useTranslation();
  const [opened, { toggle }] = useDisclosure();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { logout } = useAuth();
  const summary = useSystemSummary();
  const health = summary.data?.health;

  return (
    <AppShell header={{ height: 56 }} navbar={{ width: 220, breakpoint: "sm", collapsed: { mobile: !opened } }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group>
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <Title order={4}>{t("app.title")}</Title>
          </Group>
          <Group>
            {health && (
              <Button variant="subtle" size="compact-sm" onClick={() => navigate("/dashboard")}>
                <Group gap={6}>
                  <ThemeIcon size={10} radius="xl" color={HEALTH_COLOR[health]}>
                    <IconCircleFilled size={6} />
                  </ThemeIcon>
                  <Text size="sm">{t(`health.${health}`)}</Text>
                </Group>
              </Button>
            )}
            <Button variant="default" size="compact-sm" onClick={logout}>
              {t("app.logout")}
            </Button>
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="xs">
        {NAV.map(({ to, key, icon: Icon }) => (
          <NavLink
            key={to}
            component={RouterLink}
            to={to}
            label={t(key)}
            leftSection={<Icon size={18} stroke={1.6} />}
            active={pathname.startsWith(to)}
            onClick={() => opened && toggle()}
          />
        ))}
      </AppShell.Navbar>
      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
