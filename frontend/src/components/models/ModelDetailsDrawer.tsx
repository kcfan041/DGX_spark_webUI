import { Accordion, Badge, Button, Code, Drawer, Group, Loader, Stack, Table, Text } from "@mantine/core";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useModelDetails } from "@/api/hooks";
import { formatBytes, formatContext } from "@/lib/format";

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function ModelDetailsDrawer({ modelId, onClose }: { modelId: string | null; onClose: () => void }) {
  const { t } = useTranslation();
  const q = useModelDetails(modelId);
  const d = q.data;
  const m = d?.model;

  return (
    <Drawer opened={Boolean(modelId)} onClose={onClose} position="right" size="lg" title={m?.name ?? t("modelDetails.title")}>
      {q.isLoading || !d || !m ? (
        <Loader />
      ) : (
        <Stack data-testid="model-details">
          <Table>
            <Table.Tbody>
              <Table.Tr>
                <Table.Td w={160}>{t("models.col.size")}</Table.Td>
                <Table.Td>{formatBytes(m.size_bytes)}</Table.Td>
              </Table.Tr>
              <Table.Tr>
                <Table.Td>{t("models.col.architecture")}</Table.Td>
                <Table.Td>{m.architecture ?? t("common.unknown")}</Table.Td>
              </Table.Tr>
              <Table.Tr>
                <Table.Td>{t("models.col.quantization")}</Table.Td>
                <Table.Td>{m.quantization ?? t("modelDetails.noQuant")}</Table.Td>
              </Table.Tr>
              <Table.Tr>
                <Table.Td>{t("models.col.dtype")}</Table.Td>
                <Table.Td>{m.dtype ?? "—"}</Table.Td>
              </Table.Tr>
              <Table.Tr>
                <Table.Td>{t("models.col.maxContext")}</Table.Td>
                <Table.Td>{m.max_context ? formatContext(m.max_context) : t("common.unknown")}</Table.Td>
              </Table.Tr>
              <Table.Tr>
                <Table.Td>{t("modelDetails.kvPerToken")}</Table.Td>
                <Table.Td>
                  {m.kv_bytes_per_token ? `${formatBytes(m.kv_bytes_per_token)} / token` : t("common.unknown")}
                </Table.Td>
              </Table.Tr>
              <Table.Tr>
                <Table.Td>{t("models.col.usage")}</Table.Td>
                <Table.Td>
                  {m.in_use_by.length > 0 ? t("models.inUse", { count: m.in_use_by.length }) : t("models.unused")}
                </Table.Td>
              </Table.Tr>
            </Table.Tbody>
          </Table>
          {m.needs_remote_code && <Badge color="yellow">{t("models.remoteCode")}</Badge>}

          <Text fw={600}>{t("modelDetails.presets")}</Text>
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t("wizard.step.preset")}</Table.Th>
                <Table.Th>{t("params.max_model_len.label")}</Table.Th>
                <Table.Th>{t("params.gpu_memory_utilization.label")}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {d.presets
                .filter((p) => p.id !== "custom")
                .map((p) => (
                  <Table.Tr key={p.id}>
                    <Table.Td>
                      <Group gap={4}>
                        {t(`presets.${p.id}.label`)}
                        {p.recommended && (
                          <Badge size="xs" color="teal">
                            {t("wizard.recommended")}
                          </Badge>
                        )}
                      </Group>
                    </Table.Td>
                    <Table.Td>{formatContext(p.params.max_model_len)}</Table.Td>
                    <Table.Td>{Math.round(p.params.gpu_memory_utilization * 100)}%</Table.Td>
                  </Table.Tr>
                ))}
            </Table.Tbody>
          </Table>

          <Button component={Link} to={`/services/new?model=${encodeURIComponent(m.id)}`} onClick={onClose}>
            {t("models.createService")}
          </Button>

          <Accordion variant="contained">
            <Accordion.Item value="tech">
              <Accordion.Control>{t("modelDetails.tech")}</Accordion.Control>
              <Accordion.Panel>
                <Stack gap="xs">
                  <Text size="sm">
                    {t("modelDetails.source")}: <Code>{m.source}</Code>
                  </Text>
                  <Text size="sm">
                    {t("modelDetails.path")}: <Code>{m.host_path}</Code>
                  </Text>
                  <Text size="sm" fw={500}>
                    config.json
                  </Text>
                  <Table>
                    <Table.Tbody>
                      {Object.entries(d.config).map(([k, v]) => (
                        <Table.Tr key={k}>
                          <Table.Td w={220}>
                            <Code>{k}</Code>
                          </Table.Td>
                          <Table.Td style={{ wordBreak: "break-all" }}>{fmt(v)}</Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                  <Text size="sm" fw={500}>
                    {t("modelDetails.files", { count: d.files.length })}
                  </Text>
                  <Table>
                    <Table.Tbody>
                      {d.files.map((f) => (
                        <Table.Tr key={f.name}>
                          <Table.Td>
                            <Code>{f.name}</Code>
                          </Table.Td>
                          <Table.Td ta="right">{formatBytes(f.size)}</Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Stack>
              </Accordion.Panel>
            </Accordion.Item>
          </Accordion>
        </Stack>
      )}
    </Drawer>
  );
}
