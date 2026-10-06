import { Alert, Anchor, Button, Card, Group, Modal, Stack, Table, Text, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconAlertTriangle, IconBan, IconDownload, IconInfoCircle } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ApiError } from "@/api/client";
import { useCreateDownload, useDownloadPreview } from "@/api/hooks";
import type { DownloadPreview } from "@/api/types";
import { useApiErrorNotifier } from "@/hooks/useApiError";
import { formatBytes, formatContext } from "@/lib/format";

const BLOCKING = new Set(["TARGET_EXISTS", "NO_CONFIG", "NO_WEIGHTS", "NO_SAFETENSORS_BIN_ONLY", "DISK_SPACE_LOW"]);
const INFO = new Set(["GATED_OK"]);

const EXAMPLES = ["Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-0.5B-Instruct"];

export function DownloadModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const preview = useDownloadPreview();
  const create = useCreateDownload();
  const notifyError = useApiErrorNotifier();
  const [repo, setRepo] = useState("");
  const [dir, setDir] = useState("");
  const [result, setResult] = useState<DownloadPreview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!opened) {
      setRepo("");
      setDir("");
      setResult(null);
      setError(null);
      preview.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened]);

  const check = () => {
    setError(null);
    setResult(null);
    preview.mutate(
      { repo_id: repo.trim(), target_dir: dir.trim() || null },
      {
        onSuccess: (p) => {
          setResult(p);
          if (!dir.trim()) setDir(p.target_dir);
        },
        onError: (e) => setError(e instanceof ApiError ? e.code : "UNKNOWN"),
      },
    );
  };

  const start = () =>
    create.mutate(
      { repo_id: repo.trim(), target_dir: dir.trim() || null },
      {
        onSuccess: (d) => {
          notifications.show({ color: "teal", message: t("downloads.started", { repo: d.repo_id }) });
          onClose();
        },
        onError: notifyError,
      },
    );

  const stale = result && (result.repo_id !== repo.trim().replace(/^https:\/\/huggingface\.co\//, "") || result.target_dir !== dir.trim());

  return (
    <Modal opened={opened} onClose={onClose} title={t("downloads.title")} size="lg">
      <Stack>
        <Text size="sm" c="dimmed">
          {t("downloads.intro")}
        </Text>
        <TextInput
          label={t("downloads.repo")}
          description={t("downloads.repoHelp")}
          placeholder="Qwen/Qwen2.5-7B-Instruct"
          value={repo}
          onChange={(e) => {
            setRepo(e.currentTarget.value);
            setDir("");
            setResult(null);
            setError(null);
          }}
          onKeyDown={(e) => e.key === "Enter" && repo.trim() && check()}
          data-autofocus
          data-testid="download-repo"
          styles={{ input: { fontFamily: "monospace" } }}
        />
        <Group gap={6}>
          <Text size="xs" c="dimmed">
            {t("downloads.examples")}
          </Text>
          {EXAMPLES.map((ex) => (
            <Anchor
              key={ex}
              size="xs"
              component="button"
              type="button"
              onClick={() => {
                setRepo(ex);
                setDir("");
                setResult(null);
              }}
            >
              {ex}
            </Anchor>
          ))}
        </Group>
        <TextInput
          label={t("downloads.dir")}
          description={t("downloads.dirHelp")}
          value={dir}
          onChange={(e) => setDir(e.currentTarget.value)}
          placeholder={repo.split("/").pop() || ""}
          data-testid="download-dir"
          styles={{ input: { fontFamily: "monospace" } }}
        />
        {error && (
          <Alert color="red" icon={<IconBan size={16} />}>
            {t(`downloads.errors.${error}`, { defaultValue: t("downloads.errors.UNKNOWN") })}
            {error === "REPO_GATED" && (
              <>
                {" "}
                <Anchor component={Link} to="/settings" size="sm" onClick={onClose}>
                  {t("downloads.goToken")}
                </Anchor>
              </>
            )}
          </Alert>
        )}
        {result && !stale && (
          <Card withBorder data-testid="download-preview">
            <Table>
              <Table.Tbody>
                <Table.Tr>
                  <Table.Td w={140}>{t("downloads.size")}</Table.Td>
                  <Table.Td>
                    {formatBytes(result.size_bytes)}（{t("downloads.fileCount", { count: result.files })}）
                  </Table.Td>
                </Table.Tr>
                <Table.Tr>
                  <Table.Td>{t("downloads.diskFree")}</Table.Td>
                  <Table.Td>{formatBytes(result.disk_free_bytes)}</Table.Td>
                </Table.Tr>
                <Table.Tr>
                  <Table.Td>{t("models.col.architecture")}</Table.Td>
                  <Table.Td>{result.architecture ?? t("common.unknown")}</Table.Td>
                </Table.Tr>
                <Table.Tr>
                  <Table.Td>{t("models.col.quantization")}</Table.Td>
                  <Table.Td>{result.quantization ?? "—"}</Table.Td>
                </Table.Tr>
                <Table.Tr>
                  <Table.Td>{t("models.col.maxContext")}</Table.Td>
                  <Table.Td>{result.max_context ? formatContext(result.max_context) : t("common.unknown")}</Table.Td>
                </Table.Tr>
              </Table.Tbody>
            </Table>
            {result.warnings.length > 0 && (
              <Stack gap={6} mt="sm">
                {result.warnings.map((w) => {
                  const block = BLOCKING.has(w);
                  const info = INFO.has(w);
                  return (
                    <Alert
                      key={w}
                      p="xs"
                      color={block ? "red" : info ? "gray" : "yellow"}
                      icon={block ? <IconBan size={16} /> : info ? <IconInfoCircle size={16} /> : <IconAlertTriangle size={16} />}
                    >
                      <Text size="sm">{t(`downloads.warnings.${w}`, { dir: result.target_dir })}</Text>
                    </Alert>
                  );
                })}
              </Stack>
            )}
          </Card>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          {!result || stale ? (
            <Button onClick={check} loading={preview.isPending} disabled={!repo.trim()} data-testid="download-check">
              {t("downloads.check")}
            </Button>
          ) : (
            <Button
              leftSection={<IconDownload size={16} />}
              onClick={start}
              loading={create.isPending}
              disabled={result.blocking}
              data-testid="download-start"
            >
              {t("downloads.start", { size: formatBytes(result.size_bytes) })}
            </Button>
          )}
        </Group>
      </Stack>
    </Modal>
  );
}
