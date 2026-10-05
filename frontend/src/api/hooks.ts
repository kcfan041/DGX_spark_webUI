import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { Instance, ModelMeta, ModelSourceInfo, SystemInfo, SystemSummary } from "./types";

const POLL_MS = 3000;

export const useSystemSummary = () =>
  useQuery({ queryKey: ["system", "summary"], queryFn: () => api<SystemSummary>("/system/summary"), refetchInterval: POLL_MS });

export const useSystemInfo = () =>
  useQuery({ queryKey: ["system", "info"], queryFn: () => api<SystemInfo>("/system/info") });

export const useModels = () => useQuery({ queryKey: ["models"], queryFn: () => api<ModelMeta[]>("/models") });

export const useModelSources = () =>
  useQuery({ queryKey: ["model-sources"], queryFn: () => api<ModelSourceInfo[]>("/model-sources") });

export const useInstances = () =>
  useQuery({ queryKey: ["instances"], queryFn: () => api<Instance[]>("/instances"), refetchInterval: POLL_MS });

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
