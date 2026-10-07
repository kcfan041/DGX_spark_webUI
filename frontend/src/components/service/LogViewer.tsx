import { Badge, Box, Button, Checkbox, Group, ScrollArea, Text, TextInput } from "@mantine/core";
import { IconDownload, IconPlayerPause, IconPlayerPlay, IconSearch } from "@tabler/icons-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { getToken } from "@/api/client";
import type { LogLine } from "@/api/types";

const MAX_LINES = 3000;
const ERROR_RE = /(error|exception|traceback|failed|out of memory)/i;

async function* sseLines(url: string, signal: AbortSignal): AsyncGenerator<{ event: string; data: string }> {
  const res = await fetch(url, { headers: { Authorization: `Bearer ${getToken() ?? ""}` }, signal });
  if (!res.ok || !res.body) throw new Error(String(res.status));
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of chunk.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (data.length) yield { event, data: data.join("\n") };
    }
  }
}

interface Props {
  instanceId?: string;
  source?: string;
  height?: number;
}

export function LogViewer({ instanceId, source, height = 480 }: Props) {
  const streamPath = source
    ? `/api/v1/logs/${encodeURIComponent(source)}/stream?tail=500`
    : `/api/v1/instances/${instanceId}/logs/stream?tail=500`;
  const fileName = (source ?? `service-${instanceId}`).replace(/[^a-z0-9._-]+/gi, "-");
  const { t } = useTranslation();
  const [lines, setLines] = useState<LogLine[]>([]);
  const [live, setLive] = useState(true);
  const [ended, setEnded] = useState(false);
  const [query, setQuery] = useState("");
  const [errorsOnly, setErrorsOnly] = useState(false);
  const viewport = useRef<HTMLDivElement>(null);
  const liveRef = useRef(live);
  liveRef.current = live;

  useEffect(() => {
    setLines([]);
    setEnded(false);
    const ctrl = new AbortController();
    (async () => {
      try {
        for await (const msg of sseLines(streamPath, ctrl.signal)) {
          if (msg.event === "end") {
            setEnded(true);
            break;
          }
          const line = JSON.parse(msg.data) as LogLine;
          setLines((prev) => {
            const next = prev.length >= MAX_LINES ? prev.slice(prev.length - MAX_LINES + 1) : prev.slice();
            next.push(line);
            return next;
          });
        }
      } catch {
        if (!ctrl.signal.aborted) setEnded(true);
      }
    })();
    return () => ctrl.abort();
  }, [streamPath]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return lines.filter(
      (l) => (!q || l.text.toLowerCase().includes(q)) && (!errorsOnly || l.annotation || ERROR_RE.test(l.text)),
    );
  }, [lines, query, errorsOnly]);

  useEffect(() => {
    if (liveRef.current && viewport.current) viewport.current.scrollTo({ top: viewport.current.scrollHeight });
  }, [shown]);

  const download = () => {
    const blob = new Blob([lines.map((l) => `${l.ts ?? ""} ${l.text}`).join("\n")], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${fileName}.log`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <Box>
      <Group mb="xs" justify="space-between">
        <Group>
          <Button
            size="xs"
            variant={live ? "filled" : "default"}
            leftSection={live ? <IconPlayerPause size={14} /> : <IconPlayerPlay size={14} />}
            onClick={() => setLive((v) => !v)}
          >
            {live ? t("logs.pause") : t("logs.resume")}
          </Button>
          <Badge color={live && !ended ? "green" : "gray"} variant="dot">
            {live && !ended ? t("logs.live") : t("logs.paused")}
          </Badge>
          <TextInput
            size="xs"
            placeholder={t("logs.search")}
            leftSection={<IconSearch size={14} />}
            value={query}
            onChange={(e) => setQuery(e.currentTarget.value)}
          />
          <Checkbox
            size="xs"
            label={t("logs.errorsOnly")}
            checked={errorsOnly}
            onChange={(e) => setErrorsOnly(e.currentTarget.checked)}
          />
        </Group>
        <Button size="xs" variant="default" leftSection={<IconDownload size={14} />} onClick={download}>
          {t("logs.download")}
        </Button>
      </Group>
      <ScrollArea
        h={height}
        viewportRef={viewport}
        type="auto"
        style={{ background: "var(--mantine-color-dark-8)", borderRadius: 8 }}
        onWheel={() => {
          const v = viewport.current;
          if (v && live && v.scrollTop + v.clientHeight < v.scrollHeight - 40) setLive(false);
        }}
      >
        <Box p="xs" style={{ fontFamily: "monospace", fontSize: 12, color: "#e9ecef", whiteSpace: "pre-wrap" }}>
          {shown.length === 0 && <Text c="dimmed" size="xs">{t("logs.empty")}</Text>}
          {shown.map((l, i) => (
            <div key={i} style={{ color: l.annotation || ERROR_RE.test(l.text) ? "#ff8787" : undefined }}>
              {l.ts && <span style={{ color: "#868e96" }}>{l.ts.slice(11, 19)} </span>}
              {l.text}
              {l.annotation && (
                <div style={{ color: "#ffd43b", paddingLeft: 16 }}>
                  └ 💡 {t("logs.explain", { title: t(`errors.${l.annotation}.title`, { defaultValue: l.annotation }) })}
                </div>
              )}
            </div>
          ))}
          {ended && (
            <Text c="dimmed" size="xs" mt="xs">
              {t("logs.streamEnded")}
            </Text>
          )}
        </Box>
      </ScrollArea>
    </Box>
  );
}
