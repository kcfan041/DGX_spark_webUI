import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  ApiKeyInfo,
  AutostartProgress,
  CreatedApiKey,
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
    queryFn: () => api<{ api_base: string; models: string[] }>("/gateway/connection-info"),
    refetchInterval: POLL_MS * 2,
  });

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
    mutationFn: (name: string) => api<CreatedApiKey>("/gateway/keys", { method: "POST", body: JSON.stringify({ name }) }),
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

export function useCancelAutostart() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<AutostartProgress>("/system/autostart/cancel", { method: "POST" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["system", "autostart"] }),
  });
}
