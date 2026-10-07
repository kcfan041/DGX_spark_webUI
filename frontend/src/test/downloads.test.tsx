import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import type { DownloadPreview } from "@/api/types";
import { DownloadModal } from "@/components/models/DownloadModal";
import { DownloadsPanel } from "@/components/models/DownloadsPanel";
import zhTW from "@/i18n/locales/zh-TW.json";
import { mockFetch, renderRoute } from "./utils";

const PREVIEW: DownloadPreview = {
  repo_id: "Qwen/Qwen2.5-7B-Instruct",
  target_dir: "Qwen2.5-7B-Instruct",
  exists: false,
  files: 12,
  size_bytes: 15_231_234_048,
  disk_free_bytes: 3_700_000_000_000,
  has_config: true,
  has_weights: true,
  architecture: "Qwen2ForCausalLM",
  quantization: null,
  max_context: 32768,
  gated: false,
  warnings: [],
  blocking: false,
};

describe("DownloadModal", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("checks the repo, shows size and starts the download", async () => {
    const calls = mockFetch({
      "POST /downloads/preview": () => PREVIEW,
      "POST /downloads": () => ({ id: "d1", repo_id: PREVIEW.repo_id }),
    });
    const onClose = vi.fn();
    renderRoute(<DownloadModal opened onClose={onClose} />, "/models", "/models");

    fireEvent.change(await screen.findByTestId("download-repo"), { target: { value: "Qwen/Qwen2.5-7B-Instruct" } });
    fireEvent.click(screen.getByTestId("download-check"));
    const card = await screen.findByTestId("download-preview");
    expect(within(card).getByText(/14.2 GB/)).toBeInTheDocument();
    expect(screen.getByTestId("download-start")).toHaveTextContent("14.2 GB");
    expect(screen.getByTestId("download-dir")).toHaveValue("Qwen2.5-7B-Instruct");

    fireEvent.click(screen.getByTestId("download-start"));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(calls.find((c) => c.method === "POST" && c.url === "/api/v1/downloads")?.body).toEqual({
      repo_id: "Qwen/Qwen2.5-7B-Instruct",
      target_dir: "Qwen2.5-7B-Instruct",
    });
  });

  it("blocks when the target exists", async () => {
    mockFetch({
      "POST /downloads/preview": () => ({ ...PREVIEW, exists: true, warnings: ["TARGET_EXISTS"], blocking: true }),
    });
    renderRoute(<DownloadModal opened onClose={() => {}} />, "/models", "/models");
    fireEvent.change(await screen.findByTestId("download-repo"), { target: { value: "Qwen/Qwen2.5-7B-Instruct" } });
    fireEvent.click(screen.getByTestId("download-check"));
    await screen.findByText(/已經有「Qwen2.5-7B-Instruct」/);
    expect(screen.getByTestId("download-start")).toBeDisabled();
  });

  it("explains gated repos", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: { code: "REPO_GATED" } }), { status: 403 })),
    );
    renderRoute(<DownloadModal opened onClose={() => {}} />, "/models", "/models");
    fireEvent.change(await screen.findByTestId("download-repo"), { target: { value: "meta-llama/Llama-3.1-8B" } });
    fireEvent.click(screen.getByTestId("download-check"));
    expect(await screen.findByText(zhTW.downloads.errors.REPO_GATED)).toBeInTheDocument();
    expect(screen.getByText(zhTW.downloads.goToken)).toBeInTheDocument();
  });
});

describe("DownloadsPanel progress line", () => {
  afterEach(() => vi.unstubAllGlobals());

  const base = {
    id: "d1",
    repo_id: "Qwen/Qwen2.5-7B-Instruct",
    revision: null,
    target_dir: "Qwen2.5-7B-Instruct",
    status: "downloading",
    bytes_total: 10_000_000_000,
    bytes_done: 5_800_000_000,
    files_total: 4,
    progress: 0.58,
    error: null,
    created_at: "2026-10-08T00:00:00Z",
    started_at: "2026-10-08T00:00:00Z",
    finished_at: null,
    model_id: null,
  };

  async function lineFor(extra: Record<string, unknown>): Promise<string> {
    mockFetch({ "GET /downloads": () => [{ ...base, ...extra }] });
    renderRoute(<DownloadsPanel />, "/models", "/models");
    return (await screen.findByTestId("download-progress")).textContent ?? "";
  }

  it("shows speed and ETA when known", async () => {
    const text = await lineFor({ speed_bps: 50 * 1024 * 1024, stalled_s: 2 });
    expect(text).toContain("58%");
    expect(text).toContain("50.0 MB/s");
    expect(text).not.toContain("—");
  });

  it("says it is measuring instead of showing dashes at the start", async () => {
    const text = await lineFor({ speed_bps: null, stalled_s: 0 });
    expect(text).toContain(zhTW.downloads.measuring);
    expect(text).not.toContain("—");
  });

  it("warns only after 30s without progress", async () => {
    const text = await lineFor({ speed_bps: 0, stalled_s: 45 });
    expect(text).toContain("45 秒");
    expect(text).not.toContain("—");
  });
});
describe("download cleanup and delete errors", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows a hint when temporary files were left behind", async () => {
    mockFetch({
      "GET /downloads": () => [
        {
          id: "d1",
          repo_id: "openai/gpt-oss-20b",
          revision: null,
          target_dir: "gpt-oss-20b",
          status: "cancelled",
          bytes_total: 1,
          bytes_done: 0,
          files_total: 1,
          progress: 0,
          speed_bps: null,
          stalled_s: null,
          error: { code: "CANCELLED", leftover: "/models/.gpt-oss-20b.partial" },
          created_at: "2026-10-08T00:00:00Z",
          started_at: null,
          finished_at: "2026-10-08T00:01:00Z",
          model_id: null,
        },
      ],
    });
    renderRoute(<DownloadsPanel />, "/models", "/models");
    expect(await screen.findByTestId("download-leftover")).toHaveTextContent("/models/.gpt-oss-20b.partial");
  });

  it("shows the real reason when deleting model files fails", async () => {
    const { notifications } = await import("@mantine/notifications");
    const show = vi.spyOn(notifications, "show").mockImplementation(() => "");
    const { useApiErrorNotifier } = await import("@/hooks/useApiError");
    const { ApiError } = await import("@/api/client");
    const { renderHook } = await import("@testing-library/react");
    const { result } = renderHook(() => useApiErrorNotifier());
    result.current(
      new ApiError(500, "MODEL_DELETE_FAILED", {
        code: "MODEL_DELETE_FAILED",
        params: { error: "Directory not empty" },
      }),
    );
    expect(String(show.mock.calls[0]?.[0].message)).toContain("Directory not empty");
    expect(String(show.mock.calls[0]?.[0].message)).not.toContain("權限");
    show.mockRestore();
  });
});
