import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import type { DownloadPreview } from "@/api/types";
import { DownloadModal } from "@/components/models/DownloadModal";
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
