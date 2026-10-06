import "@/i18n";
import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import type { InstanceError } from "@/api/types";
import { StatusBadge } from "@/components/StatusBadge";
import { ErrorCard } from "@/components/service/ErrorCard";
import zhTW from "@/i18n/locales/zh-TW.json";
import en from "@/i18n/locales/en.json";
import { formatDuration, secondsSince } from "@/lib/format";
import { displayStatus } from "@/lib/status";

const wrap = (ui: React.ReactElement) => render(<MantineProvider>{ui}</MantineProvider>);

const OOM: InstanceError = {
  code: "OOM",
  severity: "error",
  params: { exit_code: 1 },
  evidence: ["ValueError: No available memory for the cache blocks."],
  suggestions: [
    { action: "edit", label_key: "errors.OOM.suggest.reduce_context", patch: { max_model_len: 8192 }, params: { value: 8192 } },
    { action: "apply_preset", label_key: "errors.OOM.suggest.low_memory", preset: "low_memory" },
  ],
  occurred_at: "2026-10-05T05:24:56Z",
};

describe("ErrorCard", () => {
  it("shows a friendly title instead of raw log, and fires suggestions", () => {
    const onSuggestion = vi.fn();
    const onLogs = vi.fn();
    wrap(<ErrorCard error={OOM} onSuggestion={onSuggestion} onViewLogs={onLogs} />);
    expect(screen.getByText(zhTW.errors.OOM.title)).toBeInTheDocument();
    expect(screen.queryByText(/No available memory/)).not.toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "降低最長對話長度至 8K 並重試" }));
    expect(onSuggestion).toHaveBeenCalledWith(OOM.suggestions[0]);
    fireEvent.click(screen.getByRole("button", { name: zhTW.detail.viewRawLog }));
    expect(onLogs).toHaveBeenCalled();
  });
});

describe("ErrorCard GPU_MEMORY_IN_USE", () => {
  it("fills numbers from error params", () => {
    const err: InstanceError = {
      code: "GPU_MEMORY_IN_USE",
      severity: "error",
      params: { free_gib: "9.2", total_gib: "121.69", requested_gib: "12.17" },
      evidence: [],
      suggestions: [
        { action: "navigate", label_key: "errors.GPU_MEMORY_IN_USE.suggest.stop_others", target: "/services" },
        { action: "edit", label_key: "errors.GPU_MEMORY_IN_USE.suggest.lower_ratio", patch: { gpu_memory_utilization: 0.05 }, params: { value: 5 } },
      ],
      occurred_at: "2026-10-05T17:17:09Z",
    };
    wrap(<ErrorCard error={err} onSuggestion={() => {}} onViewLogs={() => {}} />);
    expect(screen.getByText(/只剩約 9.2 GB 可用，但這個設定要預先保留 12.17 GB/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "把記憶體使用比例降到 5% 並重試" })).toBeInTheDocument();
  });
});

describe("StatusBadge", () => {
  it("shows error reason and unpublished state", () => {
    wrap(<StatusBadge instance={{ status: "ERROR", gateway_state: "none", phase_started_at: null, last_error: OOM }} />);
    expect(screen.getByText(`${zhTW.status.ERROR}：${zhTW.errors.OOM.title}`)).toBeInTheDocument();
    expect(displayStatus({ status: "READY", gateway_state: "failed" })).toBe("READY_UNPUBLISHED");
    expect(displayStatus({ status: "READY", gateway_state: "registered" })).toBe("READY");
  });

  it("shows elapsed time while loading", () => {
    const started = new Date(Date.now() - 133_000).toISOString();
    wrap(<StatusBadge instance={{ status: "LOADING", gateway_state: "none", phase_started_at: started, last_error: null }} />);
    expect(screen.getByText(/載入中 2 分 1[23] 秒/)).toBeInTheDocument();
  });
});

describe("format", () => {
  it("formats durations and handles naive timestamps as UTC", () => {
    expect(formatDuration(133)).toBe("2 分 13 秒");
    expect(formatDuration(7300)).toBe("2 小時 1 分");
    expect(formatDuration(5, "en")).toBe("5s");
    const now = Date.parse("2026-10-05T00:00:10Z");
    expect(secondsSince("2026-10-05T00:00:00", now)).toBe(10);
    expect(secondsSince("2026-10-05T00:00:00Z", now)).toBe(10);
  });
});

describe("i18n coverage", () => {
  const backendErrorCodes = [
    "OOM", "GPU_MEMORY_IN_USE", "MEMORY_PRECHECK", "MODEL_NOT_FOUND", "MODEL_UNSUPPORTED", "REMOTE_CODE_REQUIRED", "HEALTH_TIMEOUT",
    "CRASHED", "PORT_CONFLICT", "IMAGE_UNAVAILABLE", "GPU_UNAVAILABLE", "DOCKER_UNAVAILABLE", "CONTAINER_MISSING",
    "GATEWAY_UNREACHABLE", "GATEWAY_REGISTER_FAILED", "GATEWAY_MODEL_NOT_FOUND", "GATEWAY_PORT_IN_USE",
    "TEST_TIMEOUT", "AUTOSTART_SKIPPED_MEMORY", "UNKNOWN",
  ];
  it("has the queued phase and event", () => {
    expect(zhTW.phase.queued).toBeTruthy();
    expect(zhTW.events.queued).toBeTruthy();
    expect(zhTW.errors.OOM.suggest.raise_ratio).toContain("{{value}}");
  });

  const warningCodes = [
    "WEIGHTS_EXCEED_BUDGET",
    "NAME_INVALID", "NAME_DUPLICATE", "CONTEXT_TOO_SMALL", "CONTEXT_MODEL_UNKNOWN", "CONTEXT_EXCEEDS_MODEL",
    "MEM_UTIL_OUT_OF_RANGE", "REMOTE_CODE_ENABLED", "REMOTE_CODE_LIKELY_REQUIRED", "EXTRA_ARGS_INVALID",
    "EXTRA_ARGS_FORBIDDEN", "EXTRA_ARGS_PRESENT", "HOST_PORT_INVALID", "HOST_PORT_CONFLICT", "WEIGHTS_EXCEED_TOTAL",
    "ESTIMATE_EXCEEDS_BUDGET", "TOTAL_UTIL_HIGH", "AVAILABLE_LOW", "PAGE_CACHE_HIGH", "AUTOSTART_TOTAL_HIGH",
    "RESERVES_UP_FRONT", "RESERVE_MUCH_LARGER",
  ];

  it("has zh-TW title for every backend error code", () => {
    const errors = zhTW.errors as Record<string, unknown>;
    for (const c of backendErrorCodes) expect((errors[c] as { title?: string })?.title, c).toBeTruthy();
  });

  it("has zh-TW text for every planner warning code", () => {
    const w = zhTW.warnings as Record<string, unknown>;
    for (const c of warningCodes) expect(w[c], c).toBeTruthy();
  });

  it("english falls back (nav exists)", () => {
    expect(en.nav.services).toBe("Model Services");
  });
});
