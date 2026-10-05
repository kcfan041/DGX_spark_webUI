import { Alert, Group, Radio, Table, Text, TextInput } from "@mantine/core";
import { IconSearch } from "@tabler/icons-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ModelMeta } from "@/api/types";
import { formatBytes, formatContext } from "@/lib/format";

interface Props {
  models: ModelMeta[];
  value: string | null;
  onChange: (id: string) => void;
}

export function ModelPicker({ models, value, onChange }: Props) {
  const { t } = useTranslation();
  const [q, setQ] = useState("");
  const rows = useMemo(
    () => models.filter((m) => m.name.toLowerCase().includes(q.trim().toLowerCase())),
    [models, q],
  );
  if (models.length === 0) return <Alert>{t("wizard.noModels")}</Alert>;
  return (
    <>
      <TextInput
        placeholder={t("models.search")}
        leftSection={<IconSearch size={16} />}
        value={q}
        onChange={(e) => setQ(e.currentTarget.value)}
        mb="sm"
      />
      <Radio.Group value={value} onChange={onChange}>
        <Table highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th />
              <Table.Th>{t("models.col.name")}</Table.Th>
              <Table.Th>{t("models.col.size")}</Table.Th>
              <Table.Th>{t("models.col.quantization")}</Table.Th>
              <Table.Th>{t("models.col.maxContext")}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((m) => (
              <Table.Tr key={m.id} onClick={() => onChange(m.id)} style={{ cursor: "pointer" }}>
                <Table.Td>
                  <Radio value={m.id} aria-label={m.name} />
                </Table.Td>
                <Table.Td>
                  <Group gap={6}>
                    <Text fw={500}>{m.name}</Text>
                    {m.in_use_by.length > 0 && (
                      <Text size="xs" c="green">
                        {t("models.inUse", { count: m.in_use_by.length })}
                      </Text>
                    )}
                  </Group>
                </Table.Td>
                <Table.Td>{formatBytes(m.size_bytes)}</Table.Td>
                <Table.Td>{m.quantization ?? "—"}</Table.Td>
                <Table.Td>{m.max_context ? formatContext(m.max_context) : t("common.unknown")}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Radio.Group>
    </>
  );
}
