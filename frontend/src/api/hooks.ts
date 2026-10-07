import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  AdvancedSettings,
  AdvancedUpdate,
  ApiBaseInfo,
  EndpointTestResult,
  ApiKeyInfo,
  ConnectionInfo,
  AutostartProgress,
  CatalogModel,
  CloudModel,
  CloudProvider,
  ConnTestResult,
  CreateKeyBody,
  CreatedApiKey,
  LocalPrice,
  ProviderSpec,
  ProviderType,
  RoutingInfo,
  UpdateKeyBody,
  UsageLogPage,
  UsageSummary,
  DownloadInfo,
  DownloadPreview,
  ExternalService,
  InstanceMetrics,
  LogSource,
  ModelDetails,
  GatewayModel,
  GatewayStatus,
  Instance,
  InstanceEvent,
  InstanceParams,
  LogLine,
  ModelMeta,
  ModelSourceInfo,
  ParamField,
  Plan,
  PlanInput,
  ResolvedPreset,
  SystemInfo,
  SystemSummary,
  TestResult,
} from "./types";

const POLL_MS = 3000;
const FAST_POLL_MS = 1500;
const BUSY = new Set(["STARTING", "LOADING", "STOPPING"]);

export const useSystemSummary = () =>
  useQuery({ queryKey: ["system", "summary"], queryFn: () => api<SystemSummary>("/system/summary"), refetchInterval: POLL_MS });

export const useSystemInfo = () =>
  useQuery({ queryKey: ["system", "info"], queryFn: () => api<SystemInfo>("/system/info") });

export const useAutostart = () =>
  useQuery({ queryKey: ["system", "autostart"], queryFn: () => api<AutostartProgress>("/system/autostart"), refetchInterval: POLL_MS });

export const useModels = () => useQuery({ queryKey: ["models"], queryFn: () => api<ModelMeta[]>("/models") });

export const useModelSources = () =>
  useQuery({ queryKey: ["model-sources"], queryFn: () => api<ModelSourceInfo[]>("/model-sources") });

export const useInstances = () =>
  useQuery({ queryKey: ["instances"], queryFn: () => api<Instance[]>("/instances"), refetchInterval: POLL_MS });

export const useInstance = (id: string | undefined) =>
  useQuery({
    queryKey: ["instances", id],
    queryFn: () => api<Instance>(`/instances/${id}`),
    enabled: Boolean(id),
    refetchInterval: (q) => (q.state.data && BUSY.has(q.state.data.status) ? FAST_POLL_MS : POLL_MS),
  });

export const useInstanceEvents = (id: string | undefined) =>
  useQuery({
    queryKey: ["instances", id, "events"],
    queryFn: () => api<InstanceEvent[]>(`/instances/${id}/events`),
    enabled: Boolean(id),
    refetchInterval: POLL_MS,
  });

export const useInstanceLogs = (id: string | undefined, tail = 500, pollMs: number | false = false) =>
  useQuery({
    queryKey: ["instances", id, "logs", tail],
    queryFn: () => api<{ lines: LogLine[] }>(`/instances/${id}/logs?tail=${tail}`),
    enabled: Boolean(id),
    refetchInterval: pollMs,
  });

const enc = encodeURIComponent;

export const usePresets = (modelId: string | null) =>
  useQuery({
    queryKey: ["presets", modelId],
    queryFn: () => api<ResolvedPreset[]>(`/presets?model_id=${enc(modelId ?? "")}`),
    enabled: Boolean(modelId),
  });

export const useParamSchema = (modelId: string | null, preset: string) =>
  useQuery({
    queryKey: ["param-schema", modelId, preset],
    queryFn: () => api<ParamField[]>(`/param-schema?model_id=${enc(modelId ?? "")}&preset=${enc(preset)}`),
    enabled: Boolean(modelId),
  });

export const usePreview = (input: PlanInput | null, excludeId?: string) =>
  useQuery({
    queryKey: ["preview", input, excludeId],
    queryFn: () =>
      api<Plan>(`/instances/preview${excludeId ? `?exclude_id=${enc(excludeId)}` : ""}`, {
        method: "POST",
        body: JSON.stringify(input),
      }),
    enabled: Boolean(input?.model_id),
    placeholderData: keepPreviousData,
    retry: false,
  });

function useInvalidateInstances() {
  const qc = useQueryClient();
  return (id?: string) => {
    void qc.invalidateQueries({ queryKey: ["instances"] });
    void qc.invalidateQueries({ queryKey: ["system"] });
    void qc.invalidateQueries({ queryKey: ["models"] });
    if (id) void qc.invalidateQueries({ queryKey: ["instances", id] });
  };
}

export function useCreateInstance() {
  const invalidate = useInvalidateInstances();
  return useMutation({
    mutationFn: (body: PlanInput & { start: boolean }) =>
      api<Instance>("/instances", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: (inst) => invalidate(inst.id),
  });
}

export interface UpdateBody {
  preset?: string;
  params?: Partial<InstanceParams>;
  display_name?: string;
  served_model_name?: string;
  autostart?: boolean;
  autostart_order?: number;
  restart?: boolean;
}

export function useUpdateInstance(id: string) {
  const invalidate = useInvalidateInstances();
  return useMutation({
    mutationFn: (body: UpdateBody) =>
      api<{ instance: Instance; restart_required: boolean }>(`/instances/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => invalidate(id),
  });
}

export type LifecycleAction = "start" | "stop" | "restart" | "cancel" | "gateway/retry";

export function useLifecycle() {
  const invalidate = useInvalidateInstances();
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: LifecycleAction }) =>
      api<Instance>(`/instances/${id}/${action}`, { method: "POST" }),
    onSettled: (_d, _e, v) => invalidate(v.id),
  });
}

export function useDeleteInstance() {
  const invalidate = useInvalidateInstances();
  return useMutation({
    mutationFn: (id: string) => api<void>(`/instances/${id}`, { method: "DELETE" }),
    onSuccess: () => invalidate(),
  });
}

export function useTestInstance(id: string) {
  return useMutation({
    mutationFn: (content: string) =>
      api<TestResult>(`/instances/${id}/test`, { method: "POST", body: JSON.stringify({ content }) }),
  });
}

export function useRescanModels() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<ModelSourceInfo[]>("/model-sources/rescan", { method: "POST" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["models"] });
      void qc.invalidateQueries({ queryKey: ["model-sources"] });
    },
  });
}

export const useGatewayStatus = () =>
  useQuery({ queryKey: ["gateway", "status"], queryFn: () => api<GatewayStatus>("/gateway/status"), refetchInterval: POLL_MS * 2 });

export const useConnectionInfo = () =>
  useQuery({
    queryKey: ["gateway", "connection"],
    queryFn: () => api<ConnectionInfo>("/gateway/connection-info"),
    refetchInterval: POLL_MS * 2,
  });

export const useApiBase = () =>
  useQuery({ queryKey: ["settings", "api-base"], queryFn: () => api<ApiBaseInfo>("/settings/api-base") });

export function useUpdateApiBase() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { mode: "auto" | "manual" | null; value?: string | null }) =>
      api<ApiBaseInfo>("/settings/api-base", { method: "PUT", body: JSON.stringify(body) }),
    onSuccess: (data) => {
      qc.setQueryData(["settings", "api-base"], data);
      void qc.invalidateQueries({ queryKey: ["gateway"] });
      void qc.invalidateQueries({ queryKey: ["instances"] });
    },
  });
}

export const useGatewayModels = () =>
  useQuery({ queryKey: ["gateway", "models"], queryFn: () => api<GatewayModel[]>("/gateway/models"), refetchInterval: POLL_MS * 2 });

export const useApiKeys = () => useQuery({ queryKey: ["gateway", "keys"], queryFn: () => api<ApiKeyInfo[]>("/gateway/keys") });

function useInvalidateGateway() {
  const qc = useQueryClient();
  return () => void qc.invalidateQueries({ queryKey: ["gateway"] });
}

export function useCreateApiKey() {
  const invalidate = useInvalidateGateway();
  return useMutation({
    mutationFn: (body: CreateKeyBody) => api<CreatedApiKey>("/gateway/keys", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: invalidate,
  });
}

export function useUpdateApiKey() {
  const invalidate = useInvalidateGateway();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: UpdateKeyBody }) =>
      api<ApiKeyInfo>(`/gateway/keys/${enc(id)}`, { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: invalidate,
  });
}

export function useRotateApiKey() {
  const invalidate = useInvalidateGateway();
  return useMutation({
    mutationFn: (id: string) => api<CreatedApiKey>(`/gateway/keys/${enc(id)}/rotate`, { method: "POST" }),
    onSuccess: invalidate,
  });
}

export function useRevokeApiKey() {
  const invalidate = useInvalidateGateway();
  return useMutation({
    mutationFn: (id: string) => api<ApiKeyInfo>(`/gateway/keys/${encodeURIComponent(id)}/revoke`, { method: "POST" }),
    onSuccess: invalidate,
  });
}

export function useResync() {
  const invalidate = useInvalidateGateway();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<Record<string, number>>("/gateway/resync", { method: "POST" }),
    onSuccess: () => {
      invalidate();
      void qc.invalidateQueries({ queryKey: ["instances"] });
    },
  });
}

export function useCleanupGatewayModel() {
  const invalidate = useInvalidateGateway();
  return useMutation({
    mutationFn: (id: string) => api<void>(`/gateway/models/${encodeURIComponent(id)}/cleanup`, { method: "POST" }),
    onSuccess: invalidate,
  });
}

export const useDownloads = () =>
  useQuery({
    queryKey: ["downloads"],
    queryFn: () => api<DownloadInfo[]>("/downloads"),
    refetchInterval: (q) =>
      (q.state.data ?? []).some((d) => d.status === "queued" || d.status === "downloading") ? 1500 : 10000,
  });

function useInvalidateDownloads() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["downloads"] });
    void qc.invalidateQueries({ queryKey: ["models"] });
    void qc.invalidateQueries({ queryKey: ["model-sources"] });
  };
}

export function useDownloadPreview() {
  return useMutation({
    mutationFn: (body: { repo_id: string; target_dir?: string | null }) =>
      api<DownloadPreview>("/downloads/preview", { method: "POST", body: JSON.stringify(body) }),
  });
}

export function useCreateDownload() {
  const invalidate = useInvalidateDownloads();
  return useMutation({
    mutationFn: (body: { repo_id: string; target_dir?: string | null }) =>
      api<DownloadInfo>("/downloads", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: invalidate,
  });
}

export function useDownloadAction() {
  const invalidate = useInvalidateDownloads();
  return useMutation({
    mutationFn: async ({ id, action }: { id: string; action: "cancel" | "retry" | "delete" }): Promise<void> => {
      if (action === "delete") await api<void>(`/downloads/${id}`, { method: "DELETE" });
      else await api<DownloadInfo>(`/downloads/${id}/${action}`, { method: "POST" });
    },
    onSettled: invalidate,
  });
}

export function useDeleteModel() {
  const invalidate = useInvalidateDownloads();
  return useMutation({
    mutationFn: (modelId: string) => api<void>(`/models/${encodeURIComponent(modelId)}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
}

export const useHfToken = () =>
  useQuery({
    queryKey: ["settings", "hf-token"],
    queryFn: () => api<{ configured: boolean; source: string | null }>("/settings/hf-token"),
  });

export function useSetHfToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (token: string | null) =>
      api<{ configured: boolean; source: string | null }>("/settings/hf-token", {
        method: "PUT",
        body: JSON.stringify({ token }),
      }),
    onSuccess: (d) => qc.setQueryData(["settings", "hf-token"], d),
  });
}

export const useExternal = (enabled = true) =>
  useQuery({
    queryKey: ["system", "external"],
    queryFn: () => api<{ services: ExternalService[]; total_gpu_bytes: number }>("/system/external"),
    enabled,
    refetchInterval: POLL_MS * 2,
  });

export const useInstanceMetrics = (id: string | undefined) =>
  useQuery({
    queryKey: ["instances", id, "metrics"],
    queryFn: () => api<InstanceMetrics>(`/instances/${id}/metrics`),
    enabled: Boolean(id),
    refetchInterval: POLL_MS * 2,
  });

export const useLogSources = () =>
  useQuery({ queryKey: ["logs", "sources"], queryFn: () => api<LogSource[]>("/logs/sources"), refetchInterval: POLL_MS * 3 });

export const useModelDetails = (id: string | null) =>
  useQuery({
    queryKey: ["model-details", id],
    queryFn: () => api<ModelDetails>(`/model-details/${encodeURIComponent(id ?? "")}`),
    enabled: Boolean(id),
  });

export const useAdvancedSettings = () =>
  useQuery({ queryKey: ["settings", "advanced"], queryFn: () => api<AdvancedSettings>("/settings/advanced") });

export function useUpdateAdvanced() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AdvancedUpdate) =>
      api<AdvancedSettings>("/settings/advanced", { method: "PUT", body: JSON.stringify(body) }),
    onSuccess: (d) => {
      qc.setQueryData(["settings", "advanced"], d);
      void qc.invalidateQueries({ queryKey: ["system", "info"] });
    },
  });
}

export function useTestHfEndpoint() {
  return useMutation({
    mutationFn: (endpoint: string | null) =>
      api<EndpointTestResult>("/settings/advanced/test-hf-endpoint", {
        method: "POST",
        body: JSON.stringify({ endpoint }),
      }),
  });
}

export function useCancelAutostart() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<AutostartProgress>("/system/autostart/cancel", { method: "POST" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["system", "autostart"] }),
  });
}

// ---------------------------------------------------------------- cloud providers / models / routing

export const useProviderTypes = () =>
  useQuery({ queryKey: ["cloud", "types"], queryFn: () => api<ProviderSpec[]>("/cloud/provider-types"), staleTime: Infinity });

export const useProviders = () =>
  useQuery({ queryKey: ["cloud", "providers"], queryFn: () => api<CloudProvider[]>("/cloud/providers") });

export const useCloudModels = () =>
  useQuery({ queryKey: ["cloud", "models"], queryFn: () => api<CloudModel[]>("/cloud/models") });

export const useCatalog = (type: ProviderType | null) =>
  useQuery({
    queryKey: ["cloud", "catalog", type],
    queryFn: () => api<CatalogModel[]>(`/cloud/catalog/${type}`),
    enabled: Boolean(type),
    staleTime: 10 * 60_000,
  });

export const useRouting = () => useQuery({ queryKey: ["cloud", "routing"], queryFn: () => api<RoutingInfo>("/cloud/routing") });

function useInvalidateCloud() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["cloud"] });
    void qc.invalidateQueries({ queryKey: ["gateway"] });
  };
}

export interface ProviderBody {
  type?: ProviderType;
  name?: string;
  api_key?: string | null;
  api_base?: string | null;
}

export function useCreateProvider() {
  const invalidate = useInvalidateCloud();
  return useMutation({
    mutationFn: (body: ProviderBody) => api<CloudProvider>("/cloud/providers", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: invalidate,
  });
}

export function useUpdateProvider() {
  const invalidate = useInvalidateCloud();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ProviderBody }) =>
      api<CloudProvider>(`/cloud/providers/${enc(id)}`, { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: invalidate,
  });
}

export function useDeleteProvider() {
  const invalidate = useInvalidateCloud();
  return useMutation({
    mutationFn: (id: string) => api<{ removed_models: string[] }>(`/cloud/providers/${enc(id)}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
}

export function useTestProvider() {
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: ProviderBody & { model?: string | null } }) =>
      api<ConnTestResult>(id ? `/cloud/providers/${enc(id)}/test` : "/cloud/test", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}

export interface CloudModelBody {
  provider_id: string;
  model: string;
  name?: string | null;
  input_per_mtok?: number | null;
  output_per_mtok?: number | null;
}

export function useAddCloudModel() {
  const invalidate = useInvalidateCloud();
  return useMutation({
    mutationFn: (body: CloudModelBody) => api<CloudModel>("/cloud/models", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: invalidate,
  });
}

export function useDeleteCloudModel() {
  const invalidate = useInvalidateCloud();
  return useMutation({
    mutationFn: (id: string) => api<void>(`/cloud/models/${enc(id)}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
}

export function useSetFallback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { model: string; targets: string[] }) =>
      api<RoutingInfo>("/cloud/routing/fallbacks", { method: "PUT", body: JSON.stringify(body) }),
    onSuccess: (d) => qc.setQueryData(["cloud", "routing"], d),
  });
}

export function useSetRetries() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (num_retries: number) =>
      api<RoutingInfo>("/cloud/routing/retries", { method: "PUT", body: JSON.stringify({ num_retries }) }),
    onSuccess: (d) => qc.setQueryData(["cloud", "routing"], d),
  });
}

// ---------------------------------------------------------------- usage

const tz = () => new Date().getTimezoneOffset();

export const useUsageSummary = (start: string, end: string) =>
  useQuery({
    queryKey: ["usage", "summary", start, end],
    queryFn: () => api<UsageSummary>(`/usage/summary?start=${start}&end=${end}&tz=${tz()}`),
    placeholderData: keepPreviousData,
    refetchInterval: 60_000,
  });

export interface UsageLogFilter {
  start: string;
  end: string;
  page: number;
  model?: string | null;
  key_id?: string | null;
  status?: "success" | "failure" | null;
}

export const useUsageLogs = (f: UsageLogFilter) =>
  useQuery({
    queryKey: ["usage", "logs", f],
    queryFn: () => {
      const q = new URLSearchParams({ start: f.start, end: f.end, page: String(f.page), page_size: "50", tz: String(tz()) });
      if (f.model) q.set("model", f.model);
      if (f.key_id) q.set("key_id", f.key_id);
      if (f.status) q.set("status", f.status);
      return api<UsageLogPage>(`/usage/logs?${q.toString()}`);
    },
    placeholderData: keepPreviousData,
  });

// ---------------------------------------------------------------- local price / admin token

export const useLocalPrice = (id: string | undefined) =>
  useQuery({
    queryKey: ["instances", id, "price"],
    queryFn: () => api<LocalPrice>(`/instances/${id}/price`),
    enabled: Boolean(id),
  });

export function useSetLocalPrice(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: LocalPrice) => api<LocalPrice>(`/instances/${id}/price`, { method: "PUT", body: JSON.stringify(body) }),
    onSuccess: (d) => qc.setQueryData(["instances", id, "price"], d),
  });
}

export const useAdminTokenInfo = () =>
  useQuery({ queryKey: ["auth", "token"], queryFn: () => api<{ source: "web" | "env" }>("/auth/token") });

export function useChangeAdminToken() {
  return useMutation({
    mutationFn: (body: { current: string; new: string }) =>
      api<{ source: "web" | "env" }>("/auth/token", { method: "PUT", body: JSON.stringify(body) }),
  });
}