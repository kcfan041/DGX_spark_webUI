import { Badge, Card, Group, List, Popover, SimpleGrid, Stack, Text, UnstyledButton } from "@mantine/core";
import { IconCheck } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import type { ResolvedPreset } from "@/api/types";
import { formatContext } from "@/lib/format";

interface Props {
  presets: ResolvedPreset[];
  value: string;
  onChange: (id: string) => void;
}

export function PresetCards({ presets, value, onChange }: Props) {
  const { t } = useTranslation();
  return (
    <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
      {presets.map((p) => {
        const selected = p.id === value;
        const fmt = (v: unknown) => (typeof v === "number" ? formatContext(v) : String(v));
        return (
          <UnstyledButton key={p.id} onClick={() => onChange(p.id)} aria-pressed={selected} data-testid={`preset-${p.id}`}>
            <Card
              withBorder
              h="100%"
              style={{
                borderColor: selected ? "var(--mantine-primary-color-filled)" : undefined,
                borderWidth: selected ? 2 : 1,
              }}
            >
              <Stack gap={6}>
                <Group justify="space-between">
                  <Group gap={6}>
                    <Text fw={600}>{t(`presets.${p.id}.label`)}</Text>
                    {p.recommended && (
                      <Badge size="xs" color="teal">
                        {t("wizard.recommended")}
                      </Badge>
                    )}
                  </Group>
                  {selected && <IconCheck size={18} color="var(--mantine-primary-color-filled)" />}
                </Group>
                <Text size="sm" c="dimmed">
                  {t(`presets.${p.id}.description`)}
                </Text>
                <Text size="sm">{t("presets.context", { value: formatContext(p.params.max_model_len) })}</Text>
                <Text size="sm">{t("presets.memory", { value: Math.round(p.params.gpu_memory_utilization * 100) })}</Text>
                {p.explanations.length > 0 && (
                  <Popover width={300} withArrow shadow="md">
                    <Popover.Target>
                      <Text
                        size="xs"
                        c="blue"
                        style={{ cursor: "pointer", width: "fit-content" }}
                        onClick={(e) => e.stopPropagation()}
                      >
                        {t("wizard.why")}
                      </Text>
                    </Popover.Target>
                    <Popover.Dropdown onClick={(e) => e.stopPropagation()}>
                      <List size="xs" spacing={4}>
                        {p.explanations.map((e) => (
                          <List.Item key={e.field}>
                            <b>{t(`params.${e.field}.label`, { defaultValue: e.field })}</b>：
                            {t(e.key, {
                              ...e.params,
                              value:
                                e.field === "gpu_memory_utilization" && typeof e.params.value === "number"
                                  ? `${Math.round(e.params.value * 100)}%`
                                  : fmt(e.params.value),
                              model_max: fmt(e.params.model_max),
                            })}
                          </List.Item>
                        ))}
                      </List>
                    </Popover.Dropdown>
                  </Popover>
                )}
              </Stack>
            </Card>
          </UnstyledButton>
        );
      })}
    </SimpleGrid>
  );
}
